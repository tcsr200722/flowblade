"""
    Flowblade Movie Editor is a nonlinear video editor.
    Copyright 2012 Janne Liljeblad.

    This file is part of Flowblade Movie Editor <https://github.com/jliljebl/flowblade/>.

    Flowblade Movie Editor is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    Flowblade Movie Editor is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with Flowblade Movie Editor.  If not, see <http://www.gnu.org/licenses/>.
"""

"""
Module creates GUI editors for editable mlt properties.
"""

from gi.repository import Gtk, Gdk, GObject, GLib

import cairo

import appconsts
import cairoarea
import callbackbridge
from editorstate import PROJECT
from editorstate import PLAYER
from editorstate import current_sequence
import extraeditors
import gui
import guiutils
import gtkbuilder
import keyframeeditor
import mltfilters
import mlttransitions
import propertyparse
import propertyedit
import respaths
import translations
import updater
import utils
import utilsgtk

EDITOR = "editor"

# editor types and args                                     editor component or arg description
SLIDER = "slider"                                           # Gtk.HScale                              
BOOLEAN_CHECK_BOX = "booleancheckbox"                       # Gtk.CheckButton
COMBO_BOX = "combobox"                                      # Gtk.Combobox
KEYFRAME_EDITOR = "keyframe_editor"                         # keyfremeeditor.KeyFrameEditor that has all the key frames relative to MEDIA start
KEYFRAME_EDITOR_CLIP = "keyframe_editor_clip"               # keyfremeeditor.KeyFrameEditor that has all the key frames relative to CLIP start
KEYFRAME_EDITOR_CLIP_FADE = "keyframe_editor_clip_fade"     # Compositor keyfremeeditor.KeyFrameEditor that has all the key frames relative to CLIP start, with fade buttons
KEYFRAME_EDITOR_CLIP_FADE_FILTER = "keyframe_editor_clip_fade_filter"  # Filter keyfremeeditor.KeyFrameEditor that has all the key frames relative to CLIP start, with fade buttons
KEYFRAME_EDITOR_RELEASE = "keyframe_editor_release"         # HACK, HACK. used to prevent property update crashes in slider keyfremeeditor.KeyFrameEditor
COLOR_SELECT = "color_select"                               # Gtk.ColorButton
GEOMETRY_EDITOR = "geometry_editor"                         # keyframeeditor.GeometryEditor
FILTER_RECT_GEOM_EDITOR = "filter_rect_geometry_editor"     # keyframeeditor.FilterRectGeometryEditor
FILTER_ROTATION_GEOM_EDITOR = "filter_rotation_geometry_editor" # Creates a single editor for multiple geometry values for using in filter 
FILTER_WIPE_SELECT = "filter_wipe_select"                   # Gtk.Combobox with options from mlttransitions.wipe_lumas
COMBO_BOX_OPTIONS = "cbopts"                                # List of options for combo box editor displayed to user
LADSPA_SLIDER = "ladspa_slider"                             # Gtk.HScale, does ladspa update for release changes(disconnect, reconnect)
CLIP_FRAME_SLIDER = "clip_frame_slider"                     # Gtk.HScale, range 0 - clip length in frames
COLOR_CORRECTOR = "color_corrector"                         # 3 band color corrector color circle and Lift Gain Gamma sliders
CR_CURVES = "crcurves"                                      # Curves color editor with Catmull-Rom curve
COLOR_BOX = "colorbox"                                      # One band color editor with color box interface
COLOR_LGG = "colorlgg"                                      # Editor for ColorLGG filter
FILE_SELECTOR = "file_select"                               # File selector button for selecting single files from
FILE_TYPES = "file_types"                                   # list of files types with "." characters, like ".png.tga.bmp"
FADE_LENGTH = "fade_length"                                 # Autofade compositors fade length
TEXT_ENTRY = "text_entry"                                   # Text editor
ROTOMASK = "rotomask"                                       # Displays info and launches rotomask window
NO_KF_RECT = "no_keyframes_rect"                            # keyframeeditor.GeometryNoKeyframes, no keyframes here, machinery for creating this type GUI editors just assumes keyframes
GRADIENT_TINT = "gradient_tint_editor"                      # editor for Gradient Tint, "frei0r.cairogradient" MLT filter 
CROP_EDITOR = "crop_editor"                                 # editor for Crop filter
ALPHA_SHAPE_EDITOR = "alpha_shape_editor"                   # editor for Alpha Shape filter
NO_EDITOR = "no_editor"                                     # No editor displayed for property

COMPOSITE_EDITOR_BUILDER = "composite_properties"           # Creates a single row editor for multiple properties of composite transition
REGION_EDITOR_BUILDER = "region_properties"                 # Creates a single row editor for multiple properties of region transition
ROTATION_GEOMETRY_EDITOR_BUILDER = "rotation_geometry_editor" # Creates a single editor for multiple geometry values
INFOANDTIPS = "infotips"                                    # Displays link to docs Info & Tips page 
ANALYZE_STABILIZE = "analyzestabilize"                      # Launches stabilizing analysis for clip
ANALYZE_MOTION = "analyzemotion"                            # Launches motion tracking analysis for clip
APPLY_MOTION = "applymotion"                                # Applies motion tracking as source image movement.
APPLY_FILTER_MASK_MOTION = "applyfiltermaskmotion"          # Applies motion tracking as filter mask.
SCALE_DIGITS = "scale_digits"                               # Number of decimal digits displayed in a widget

# We need to use globals to change slider -> kf editor and back because the data does not (can not) exist anywhere else. FilterObject.properties are just tuples and EditableProperty objects
# are created deterministically from those and FilterObject.info.property_args data. So we need to save data here on change request to make the change happen.
# This data needs to be erased always after use.
changing_slider_to_kf_property_name = None


def _p(name):
    try:
        return translations.param_names[name]
    except KeyError:
        return name

def get_editor_row(editable_property):
    """
    Returns GUI component to edit provided editable property.
    """
    try:
        editor = editable_property.args[EDITOR]
    except KeyError:
        editor = SLIDER #default, if editor not specified
    
    create_func = EDITOR_ROW_CREATORS[editor]
    return create_func(editable_property)

def get_transition_extra_editor_rows(compositor, editable_properties):
    """
    Returns list of extraeditors GUI components.
    """
    extra_editors = compositor.transition.info.extra_editors
    rows = []
    for editor_name in extra_editors:
        try:
            create_func = EDITOR_ROW_CREATORS[editor_name]
            editor_row = create_func(compositor, editable_properties)
            rows.append(editor_row)
        except KeyError:
            print("get_transition_extra_editor_rows fail with:" + editor_name)

    return rows

def get_filter_extra_editor_rows(filt, editable_properties, track, clip_index):
    """
    Returns list of extraeditors GUI components.
    """
    extra_editors = filt.info.extra_editors
    rows = []
    for editor_name in extra_editors:
        create_func = EDITOR_ROW_CREATORS[editor_name]
        editor_row = create_func(filt, editable_properties, editor_name, track, clip_index)
        
        rows.append(editor_row)

    return rows

def get_non_mlt_property_editor_row(non_mlt_editable_property, editor):
    """
    Returns GUI component to edit provided non-mlt editable property.
    """
    create_func = EDITOR_ROW_CREATORS[editor]
    row = create_func(non_mlt_editable_property)
    row.set_margin_top(4)
    return row
    

    
# ------------------------------------------------- gui builders
def _get_two_column_editor_row(name, editor_widget):
    name = _p(name)
    label = Gtk.Label(label=name + ":")

    label_box = Gtk.HBox()
    label_box.pack_start(label, False, False, 0)
    label_box.pack_start(Gtk.Label(), True, True, 0)
    label_box.set_size_request(appconsts.PROPERTY_NAME_WIDTH, appconsts.PROPERTY_ROW_HEIGHT)
    
    hbox = Gtk.HBox(False, 2)
    hbox.pack_start(label_box, False, False, 4)
    hbox.pack_start(editor_widget, True, True, 0)
    return hbox
    
def _get_slider_row(editable_property, slider_name=None, compact=False):
    slider_editor = SliderEditor(editable_property, slider_name=None, compact=False)

    # We need to tag this somehow and add lambda to pass frame events so that this can be to set get frame events
    # in clipeffectseditor.py.
    if slider_editor.editor_type == KEYFRAME_EDITOR:
        slider_editor.vbox.is_kf_editor = True      
        slider_editor.vbox.display_tline_frame = lambda tline_frame:slider_editor.kfeditor.display_tline_frame(tline_frame)
        slider_editor.vbox.update_slider_value_display = lambda frame:slider_editor.kfeditor.update_slider_value_display(frame)
        slider_editor.vbox.update_clip_pos = lambda:slider_editor.kfeditor.update_clip_pos()

    return slider_editor.vbox
    

class SliderEditor:
    def __init__(self, editable_property, slider_name=None, compact=False):
        self.vbox = Gtk.VBox(False)
        # We are using value here as flag if this is beinfg edited by slider as a single value or by keyframe editor as changing value
        # If we find "=" this means that value is keyframe expression.
        is_multi_kf = (editable_property.value.find("=") != -1)

        global changing_slider_to_kf_property_name
        if changing_slider_to_kf_property_name == editable_property.name or is_multi_kf == True:
            eq_index = editable_property.value.find("=")
            
            # create kf in frame 0 if value PROP_INT or PROP_FLOAT
            if eq_index == -1:
                new_value = "0=" + editable_property.value
                editable_property.value = new_value
                editable_property.write_filter_object_property(new_value)
                            
            editable_property = editable_property.get_as_KeyFrameHCSFilterProperty()
            self.init_for_kf_editor(editable_property)
            
            # This has now already been used if existed and has to be deleted.
            if changing_slider_to_kf_property_name == editable_property.name:
                changing_slider_to_kf_property_name = None
        else:
            self.init_for_slider(editable_property, slider_name, compact)
        
        self.editable_property = editable_property
        
    def init_for_slider(self, editable_property, slider_name=None, compact=False):
        self.editor_type = SLIDER
        
        adjustment = editable_property.get_input_range_adjustment()
        adjustment.connect("value-changed", editable_property.adjustment_value_changed)

        hslider = Gtk.HScale()
        hslider.set_adjustment(adjustment)
        hslider.set_draw_value(False)

        spin = Gtk.SpinButton()
        spin.set_numeric(True)
        spin.set_adjustment(adjustment)

        _set_digits(editable_property, hslider, spin)

        if slider_name == None:
            name = editable_property.get_display_name()
        else:
            name = slider_name
        name = _p(name)
        
        kfs_switcher = KeyframesToggler(self)
                
        hbox = Gtk.HBox(False, 4)
        if compact:
            name_label = Gtk.Label(label=name + ":")
            hbox.pack_start(name_label, False, False, 4)
            hbox.pack_start(hslider, True, True, 0)
            hbox.pack_start(spin, False, False, 4)
            hbox.pack_start(kfs_switcher.widget, False, False, 4)
            self.vbox.pack_start(hbox, False, False, 0)
        else:
            label = Gtk.Label(label=name + ":")
            label.set_margin_start(4)
                
            label_panel = Gtk.HBox(False, 4)
            label_panel.pack_start(label, False, False, 0)            
            label_panel.pack_start(Gtk.Label(), True, True, 0)            

            vboxl = Gtk.VBox()
            vboxl.pack_start(label_panel, False, False, 0)
            vboxl.pack_start(hslider, False, False, 0)
                        
            hboxr = Gtk.HBox()
            spin.set_margin_start(4)
            hboxr.pack_start(spin, False, False, 0)
            kfs_switcher.widget.set_margin_top(6)
            hboxr.pack_start(kfs_switcher.widget, False, False, 4)

            hbox = Gtk.HBox()
            hbox.pack_start(vboxl, True, True, 0)  
            hbox.pack_start(hboxr, False, False, 0)
            hbox.set_margin_top(2)

            self.vbox.pack_start(hbox, False, False, 0)

    def init_for_kf_editor(self, editable_property):
        self.editor_type = KEYFRAME_EDITOR
        
        kfs_switcher = KeyframesToggler(self)
        self.kfeditor = keyframeeditor.KeyFrameEditor(editable_property, True, kfs_switcher)
        self.vbox.pack_start(self.kfeditor, False, False, 0)

    def kfs_toggled(self):
        if self.editor_type == SLIDER: # slider -> kf editor
            global changing_slider_to_kf_property_name
            changing_slider_to_kf_property_name = self.editable_property.name
            callbackbridge.clipeffectseditor_refresh_clip()
        else: # kf editor -> slider
            # Save value as single keyframe or PROP_INT or PROP_FLOAT and
            # drop all but first keyframe.
            # Going kf editor -> slider destroys all but first keyframe.
            first_kf_index = self.editable_property.value.find(";")
            if first_kf_index == -1:
                val = self.editable_property.value
            else:
                val = self.editable_property.value[0:first_kf_index]
            
            eq_index = self.editable_property.value.find("=")  + 1
            first_kf_val = val[eq_index:len(val)]

            # We need to turn editable property value and type back to what it was before user selected to go kf editing
            # so that it gets edited with slider on next init.
            info = self.editable_property._get_filter_object().info #.__dict__
            p_name, p_value, p_original_type = info.properties[self.editable_property.property_index]
            
            if p_original_type == appconsts.PROP_INT:
                self.editable_property.type = appconsts.PROP_INT
                try:
                    int_str_val = str(int(first_kf_val))
                except:
                    int_str_val = str(float(first_kf_val))

                self.editable_property.write_value(int_str_val)
            elif p_original_type == appconsts.PROP_FLOAT:
                self.editable_property.type = appconsts.PROP_FLOAT 

                self.editable_property.write_value(str(float(first_kf_val)))
            else:

                self.editable_property.write_value("0=" + str(float(first_kf_val)))

            callbackbridge.clipeffectseditor_refresh_clip()


class KeyframesToggler:
    def __init__(self, parent_editor):
        w=16
        h=22
        self.widget = cairoarea.CairoDrawableArea2( w,
                                                    h,
                                                    self._draw)
        self.widget.press_func = self._press_event
        self.parent_editor = parent_editor
        if parent_editor.editor_type == KEYFRAME_EDITOR:
            self.surface  = cairo.ImageSurface.create_from_png(respaths.IMAGE_PATH + "slider_icon.png")
        else:
            self.surface  = cairo.ImageSurface.create_from_png(respaths.IMAGE_PATH + "kf_active.png")

        self.surface_x  = 3
        self.surface_y  = 8

    def _draw(self, event, cr, allocation):
        cr.set_source_surface(self.surface, self.surface_x, self.surface_y)
        cr.paint()

    def _press_event(self, event):
        self.parent_editor.kfs_toggled()

def _get_ladspa_slider_row(editable_property, slider_name=None):
    adjustment = editable_property.get_input_range_adjustment()
    adjustment.connect("value-changed", editable_property.adjustment_value_changed)
        
    hslider = Gtk.HScale()
    hslider.set_adjustment(adjustment)
    hslider.set_draw_value(False)
    hslider.connect("button-release-event", lambda w, e: _ladspa_slider_update(editable_property, adjustment))
    
    spin = Gtk.SpinButton()
    spin.set_numeric(True)
    spin.set_adjustment(adjustment)
    spin.connect("button-release-event", lambda w, e: _ladspa_slider_update(editable_property, adjustment))
    spin.connect("activate", lambda w: _ladspa_spinner_update(editable_property, spin, adjustment))

    _set_digits(editable_property, hslider, spin)

    hbox = Gtk.HBox(False, 4)
    hbox.pack_start(hslider, True, True, 0)
    hbox.pack_start(spin, False, False, 4)
    if slider_name == None:
        name = editable_property.get_display_name()
    else:
        name = slider_name

    top_row = _get_two_column_editor_row(name, Gtk.HBox())
    vbox = Gtk.VBox(False)
    vbox.pack_start(top_row, True, True, 0)
    vbox.pack_start(hbox, False, False, 0)
    return vbox

def _get_no_kf_slider_row(editable_property, slider_name=None, compact=False):
    adjustment = editable_property.get_input_range_adjustment()

    hslider = Gtk.HScale()
    hslider.set_adjustment(adjustment)
    hslider.set_draw_value(False)
    hslider.connect("button-release-event", lambda w, e: _ladspa_slider_update(editable_property, adjustment))
    
    spin = Gtk.SpinButton()
    spin.set_numeric(True)
    spin.set_adjustment(adjustment)
    spin.connect("button-release-event", lambda w, e: _ladspa_slider_update(editable_property, adjustment))

    _set_digits(editable_property, hslider, spin)

    if slider_name == None:
        name = editable_property.get_display_name()
    else:
        name = slider_name

    hbox = Gtk.HBox(False, 4)
    if compact:
        name_label = Gtk.Label(label=name + ":")
        hbox.pack_start(name_label, False, False, 4)
    hbox.pack_start(hslider, True, True, 0)
    hbox.pack_start(spin, False, False, 4)

    vbox = Gtk.VBox(False)
    if compact:
        vbox.pack_start(hbox, False, False, 0)
    else:
        top_right_h = Gtk.HBox()
        top_right_h.pack_start(Gtk.Label(), True, True, 0)            
        top_row = _get_two_column_editor_row(name, top_right_h)
        
        vbox.pack_start(top_row, True, True, 0)
        vbox.pack_start(hbox, False, False, 0)
            
    return vbox

def _get_clip_frame_slider(editable_property):
    # Exceptionally we set the edit range here,
    # as the edit range is the clip length and 
    # is obviously not known at program start.
    length = editable_property.get_clip_length() - 1
    editable_property.input_range = (0, length)
    editable_property.output_range = (0.0, length)
            
    adjustment = editable_property.get_input_range_adjustment()

    hslider = Gtk.HScale()
    hslider.set_adjustment(adjustment)
    hslider.set_draw_value(False)
    hslider.connect("button-release-event", lambda w, e: _clip_frame_slider_update(editable_property, adjustment))
    
    spin = Gtk.SpinButton()
    spin.set_numeric(True)
    spin.set_adjustment(adjustment)
    spin.connect("button-release-event", lambda w, e: _clip_frame_slider_update(editable_property, adjustment))

    hslider.set_digits(0)
    spin.set_digits(0)

    hbox = Gtk.HBox(False, 4)
    hbox.pack_start(hslider, True, True, 0)
    hbox.pack_start(spin, False, False, 4)

    name = editable_property.get_display_name()
    return _get_two_column_editor_row(name, hbox)
   
def _get_affine_slider(name, adjustment):
    hslider = Gtk.HScale()
    hslider.set_adjustment(adjustment)
    hslider.set_draw_value(False)
    
    spin = Gtk.SpinButton()
    spin.set_numeric(True)
    spin.set_adjustment(adjustment)

    hslider.set_digits(0)
    spin.set_digits(0)

    hbox = Gtk.HBox(False, 4)
    hbox.pack_start(hslider, True, True, 0)
    hbox.pack_start(spin, False, False, 4)

    return (hslider, spin, _get_two_column_editor_row(name, hbox))

def _get_text_entry(editable_property):
    entry = Gtk.Entry.new()
    entry.set_text(editable_property.value)
    entry.connect("changed", lambda w: _entry_contentents_changed(w, editable_property))

    hbox = Gtk.HBox(False, 4)
    hbox.pack_start(entry, True, True, 0)

    return _get_two_column_editor_row(editable_property.get_display_name(), hbox)

def _entry_contentents_changed(entry, editable_property):
     editable_property.value = entry.get_text()
 
def _get_boolean_check_box_row(editable_property, compact=False):
    check_button = Gtk.CheckButton()
    check_button.set_active(editable_property.value == "1")
    check_button.connect("toggled", editable_property.boolean_button_toggled)
    
    if compact:
        return guiutils.get_right_expand_box(Gtk.Label(label=editable_property.get_display_name() + ":"), check_button, True)
    else:
        hbox = Gtk.HBox(False, 4)

        hbox.pack_start(check_button, False, False, 4)
        hbox.pack_start(Gtk.Label(), True, True, 0)
        
        return _get_two_column_editor_row(editable_property.get_display_name(), hbox)

def _get_combo_box_row(editable_property, compact=False):
    combo_box = Gtk.ComboBoxText()
            
    # Parse options and fill combo box
    opts_str = editable_property.args[COMBO_BOX_OPTIONS]
    values = []
    opts = opts_str.split(",")
    for option in opts:
        sides = option.split(":")   
        values.append(sides[1])
        opt = sides[0].replace("!"," ")# Spaces are separators in args
                                       # and are replaced with "!" characters for names
        opt = translations.get_combo_option(opt)
        combo_box.append_text(opt) 

    # Set initial value
    selection = values.index(editable_property.value)
    combo_box.set_active(selection)
    
    combo_box.connect("changed", editable_property.combo_selection_changed, values)  

    if compact:
        return guiutils.get_right_expand_box(Gtk.Label(label=editable_property.get_display_name() + ":"), combo_box, True)
    else:
        return _get_two_column_editor_row(editable_property.get_display_name(), combo_box)

def _get_color_selector(editable_property):
    gdk_color = editable_property.get_value_rgba()
    color_button = Gtk.ColorButton.new_with_rgba(Gdk.RGBA(*gdk_color))
    color_button.connect("color-set", editable_property.color_selected)

    picker_button = Gtk.ToggleButton()
    gtkbuilder.button_set_image_icon_name(picker_button, Gtk.STOCK_COLOR_PICKER)
    
    info_label = Gtk.Label()
    
    editable_property.picker_toggled_id = picker_button.connect("toggled", _color_selector_picker_toggled, editable_property, color_button, info_label)

    hbox = Gtk.HBox(False, 4)
    hbox.pack_start(color_button, False, False, 4)
    hbox.pack_start(picker_button, False, False, 4)
    hbox.pack_start(info_label, False, False, 4)
    hbox.pack_start(Gtk.Label(), True, True, 0)
    
    return _get_two_column_editor_row(editable_property.get_display_name(), hbox)

def _color_selector_picker_toggled(picker_button, editable_property, color_button, info_label):
    gdk_window = gui.editor_window.window.get_window()
    if picker_button.get_active() == True:
        editable_property.cp_window_press_id = gui.editor_window.window.connect('button-press-event', _color_picker_window_press_event, editable_property, picker_button, color_button, info_label)
        editable_property.cp_monitor_press_id = gui.tline_display.connect('button-press-event', _color_picker_monitor_press_event, editable_property, picker_button, color_button, info_label)
        info_label.set_markup("<small>" + _("Click Monitor to Select Color") + "</small>")
    else:
        _maybe_disconnect_color_picker_listeners(editable_property)
        info_label.set_markup("")
        
def _color_picker_window_press_event(widget, event, editable_property, picker_button, color_button, info_label):
    # Exit expecting color selection
    _maybe_disconnect_color_picker_listeners(editable_property)
    _maybe_untoggle_picker_botton(editable_property, picker_button)

    info_label.set_markup("")
    
    return True
    
def _color_picker_monitor_press_event(widget, event, editable_property, picker_button, color_button, info_label):
    # Exit expecting color selection
    _maybe_disconnect_color_picker_listeners(editable_property)
    _maybe_untoggle_picker_botton(editable_property, picker_button)

    try:
        # Get selected image coordinate.
        alloc = widget.get_allocation()
        window_width = alloc.width
        window_height = alloc.height
        
        width = PROJECT().profile.width()
        height = PROJECT().profile.height()
        display_ratio = float(width) / float(height) # mlt_properties_get_double( properties, "display_ratio" );
        
        if window_height * display_ratio > window_width:
            rect_w = window_width
            rect_h = int(float(window_width) / float(display_ratio))
        else:
            rect_w = int(float(window_height) * float(display_ratio))
            rect_h = window_height

        rect_x = int(float( window_width - rect_w ) / 2.0)
        rect_x -= rect_x % 2
        rect_y = int(float(window_height - rect_h ) / 2.0)

        x = event.x - rect_x
        y = event.y - rect_y

        img_x = int((float(x)/float(rect_w)) * float(width))
        img_y = int((float(y)/float(rect_h)) * float(height))
        
        # Get selected color 
        rgb_data = PLAYER().seek_and_get_rgb_frame(PLAYER().current_frame(), update_gui=False)
        pixel = (img_y * 1920 + img_x) * 4
        r = rgb_data[pixel]
        g = rgb_data[pixel + 1]
        b = rgb_data[pixel + 2]
    except:
        r = 0
        g = 0
        b = 0

    # Set selected color as color button selection and property value.
    color = Gdk.RGBA(float(r)/255.0, float(g)/255.0, float(b)/255.0, 1.0)

    color_button.set_rgba(color)
    editable_property.color_selected(color_button)

    info_label.set_markup("")
        
    return True
         
def _maybe_disconnect_color_picker_listeners(editable_property):
    if editable_property.cp_window_press_id != -1:
        gui.editor_window.window.disconnect(editable_property.cp_window_press_id)
        gui.tline_display.disconnect(editable_property.cp_monitor_press_id)
        editable_property.cp_window_press_id = -1
        editable_property.cp_monitor_press_id = -1

def _maybe_untoggle_picker_botton(editable_property, picker_button):
    if picker_button.get_active() == True:
        picker_button.handler_block(editable_property.picker_toggled_id)
        picker_button.set_active(False)
        picker_button.handler_unblock(editable_property.picker_toggled_id)

def _get_filter_wipe_selector(editable_property):
    # Preset luma
    combo_box = Gtk.ComboBoxText()
            
    # Get options
    keys = list(mlttransitions.wipe_lumas.keys())
    # translate here
    keys.sort()
    for k in keys:
        combo_box.append_text(k)
 
    # Set initial value
    k_index = -1
    tokens = editable_property.value.split("/")
    test_value = tokens[len(tokens) - 1]
    for k,v in mlttransitions.wipe_lumas.items():
        if v == test_value:
            k_index = keys.index(k)
    
    combo_box.set_active(k_index)
    combo_box.connect("changed", editable_property.combo_selection_changed, keys)
    return _get_two_column_editor_row(editable_property.get_display_name(), combo_box)

class FadeLengthEditor(Gtk.HBox):
    def __init__(self, editable_property):

        GObject.GObject.__init__(self)
        self.set_homogeneous(False)
        self.set_spacing(2)
        
        self.editable_property = editable_property
        length = self.editable_property.clip.clip_out - self.editable_property.clip.clip_in + 1
        
        name = editable_property.get_display_name()
        name = _p(name)
        name_label = Gtk.Label(label=name + ":")
        
        label_box = Gtk.HBox()
        label_box.pack_start(name_label, False, False, 0)
        label_box.pack_start(Gtk.Label(), True, True, 0)
        label_box.set_size_request(appconsts.PROPERTY_NAME_WIDTH, appconsts.PROPERTY_ROW_HEIGHT)
           
        self.spin = Gtk.SpinButton.new_with_range (1, 1000, 1)
        self.spin.set_numeric(True)
        self.spin.set_value(length)
        self.spin.connect("value-changed", self.spin_value_changed)

        self.pack_start(guiutils.pad_label(4,4), False, False, 0)
        self.pack_start(label_box, False, False, 0)
        self.pack_start(self.spin, False, False, 0)
        self.pack_start(Gtk.Label(), True, True, 0)
        
    def spin_value_changed(self, spin):
        if self.editable_property.clip.transition.info.name == "##auto_fade_in":
            self.editable_property.clip.set_length_from_in(int(spin.get_value()))
        else:
            self.editable_property.clip.set_length_from_out(int(spin.get_value()))

        updater.repaint_tline()
    
    def display_tline_frame(self, frame):
        pass # We don't seem to need this after all, panel gets recreated after compositor length change.
        
def _get_fade_length_editor(editable_property):
    return FadeLengthEditor(editable_property)

def _get_file_select_editor(editable_property):
    """
    Returns GUI component for selecting file of determined type
    """
    dialog = Gtk.FileChooserDialog(_("Select File"), None, 
                                   Gtk.FileChooserAction.OPEN, 
                                   (_("Cancel"), Gtk.ResponseType.CANCEL,
                                    _("OK"), Gtk.ResponseType.ACCEPT))
    dialog.set_action(Gtk.FileChooserAction.OPEN)
    dialog.set_transient_for(gui.editor_window.window)
    #dialog.set_select_multiple(False)

    try:
        file_types_args_list = editable_property.args[FILE_TYPES].split(".")
        file_types_args_list = file_types_args_list[1:len(file_types_args_list)]
        file_filter = Gtk.FileFilter()
        for file_type in file_types_args_list:
            file_filter.add_pattern("*." + file_type)
        file_filter.set_name("Accepted Files")
        
        dialog.add_filter(file_filter)
    except:
        # We will interpret missing as decision to add no file filter.
        pass
        
    file_select_button = gtkbuilder.get_file_chooser_button_with_dialog(dialog)
    file_select_button.set_size_request(210, 28)
    # TODO: check this out
    if hasattr(editable_property, "value") and editable_property.value != '' and editable_property.value != '""':
        file_select_button.set_filename(editable_property.value)

    file_select_label = Gtk.Label(label=editable_property.get_display_name())

    editor_row = Gtk.HBox(False, 2)
    editor_row.pack_start(file_select_label, False, False, 2)
    editor_row.pack_start(guiutils.get_pad_label(3, 5), False, False, 2)
    editor_row.pack_start(file_select_button, False, False, 0)

    dialog.connect('response', editable_property.dialog_response_callback)

    return editor_row
    
def _create_composite_editor(clip, editable_properties):
    aligned = [ep for ep in editable_properties if ep.name == "aligned"][0]
    distort = [ep for ep in editable_properties if ep.name == "distort"][0]
    operator = [ep for ep in editable_properties if ep.name == "operator"][0]
    values = ["over","and","or","xor"]
    deinterlace = [ep for ep in editable_properties if ep.name == "deinterlace"][0]
    progressive = [ep for ep in editable_properties if ep.name == "progressive"][0]
    force_values = [_("Nothing"),_("Progressive"),_("Deinterlace"),_("Both")]

    combo_box = Gtk.ComboBoxText()
    for val in force_values:
        combo_box.append_text(val)
    selection = _get_force_combo_index(deinterlace, progressive)
    combo_box.set_active(selection)
    combo_box.connect("changed", _compositor_editor_force_combo_box_callback, (deinterlace, progressive))
    force_vbox = Gtk.VBox(False, 4)
    force_vbox.pack_start(Gtk.Label(label=_("Force")), True, True, 0)
    force_vbox.pack_start(combo_box, True, True, 0)

    hbox = Gtk.HBox(False, 4)
    hbox.pack_start(guiutils.get_pad_label(3, 5), False, False, 0)
    hbox.pack_start(_get_boolean_check_box_button_column(_("Align"), aligned), False, False, 0)
    hbox.pack_start(_get_boolean_check_box_button_column(_("Distort"), distort), False, False, 0)
    hbox.pack_start(Gtk.Label(), True, True, 0)
    # THESE ARE DISABLED BECAUSE CHANGING ALPHA MODE CAN MAKE PROJECTS UNOPENABLE IF AFFECTED 
    # COMPOSITOR IS ON THE FIRST FRAME
    #hbox.pack_start(_get_combo_box_column(_("Alpha"), values, operator), False, False, 0)
    #hbox.pack_start(Gtk.Label(), True, True, 0)
    hbox.pack_start(force_vbox, False, False, 0)
    hbox.pack_start(guiutils.get_pad_label(3, 5), False, False, 0)
    return hbox

def _compositor_editor_force_combo_box_callback(combo_box, data):
    value = combo_box.get_active()
    deinterlace, progressive = data
    # these must correspond to hardcoded values ["Nothing","Progressive","Deinterlace","Both"] above
    if value == 0:
        deinterlace.write_value("0")
        progressive.write_value("0")
    elif value == 1:
        deinterlace.write_value("0")
        progressive.write_value("1")
    elif value == 2:
        deinterlace.write_value("1")
        progressive.write_value("0")
    else:
        deinterlace.write_value("1")
        progressive.write_value("1")

def _create_rotion_geometry_editor(clip, editable_properties):   
    ep = create_rotating_geometry_editor_property(clip, editable_properties)
    kf_edit = keyframeeditor.RotatingGeometryEditor(ep, False)
    return kf_edit

def create_rotating_geometry_editor_property(clip, editable_properties):
    # Build a custom object that duck types for TransitionEditableProperty 
    # to be used in editor keyframeeditor.RotatingGeometryEditor.
    ep = utils.EmptyClass()
    # pack real properties to go
    ep.x = [ep for ep in editable_properties if ep.name == "x"][0]
    ep.y = [ep for ep in editable_properties if ep.name == "y"][0]
    ep.x_scale = [ep for ep in editable_properties if ep.name == "x scale"][0]
    ep.y_scale = [ep for ep in editable_properties if ep.name == "y scale"][0]
    ep.rotation = [ep for ep in editable_properties if ep.name == "rotation"][0]
    ep.opacity = [ep for ep in editable_properties if ep.name == "opacity"][0]
    # Screen width and height are needed for frei0r conversions
    ep.profile_width = current_sequence().profile.width()
    ep.profile_height = current_sequence().profile.height()
    # duck type methods, using opacity is not meaningful, any property with clip member could do
    ep.get_clip_tline_pos = lambda : ep.opacity.clip.clip_in # clip is compositor, compositor in and out points are straight in timeline frames
    ep.get_clip_length = lambda : ep.opacity.clip.clip_out - ep.opacity.clip.clip_in + 1
    ep.get_input_range_adjustment = lambda : Gtk.Adjustment(value=float(100), lower=float(0), upper=float(100), step_increment=float(1))
    ep.get_display_name = lambda : "Opacity"
    ep.get_pixel_aspect_ratio = lambda : (float(current_sequence().profile.sample_aspect_num()) / current_sequence().profile.sample_aspect_den())
    ep.get_in_value = lambda out_value : out_value # hard coded for opacity 100 -> 100 range
    ep.write_out_keyframes = lambda w_kf : propertyparse.rotating_ge_write_out_keyframes(ep, w_kf)
    ep.update_prop_value = lambda : propertyparse.rotating_ge_update_prop_value(ep) # This is needed to get good update after adding kfs with fade buttons, iz all kinda fugly
                                                                                    # We need this to reinit GUI components after programmatically added kfs.
    x_tokens = ep.x.value.split(";")
    y_tokens = ep.y.value.split(";")
    x_scale_tokens = ep.x_scale.value.split(";")
    y_scale_tokens = ep.y_scale.value.split(";")
    rotation_tokens = ep.rotation.value.split(";")
    opacity_tokens = ep.opacity.value.split(";")
    
    value = ""
    for i in range(0, len(x_tokens)): # these better match, same number of keyframes for all values, or this will not work
        frame, x, kf_type = propertyparse._get_roto_geom_frame_value(x_tokens[i])
        frame, y, kf_type = propertyparse._get_roto_geom_frame_value(y_tokens[i])
        frame, x_scale, kf_type = propertyparse._get_roto_geom_frame_value(x_scale_tokens[i])
        frame, y_scale, kf_type = propertyparse._get_roto_geom_frame_value(y_scale_tokens[i])
        frame, rotation, kf_type = propertyparse._get_roto_geom_frame_value(rotation_tokens[i])
        frame, opacity, kf_type = propertyparse._get_roto_geom_frame_value(opacity_tokens[i])

        eq_str = propertyparse._get_eq_str(kf_type)

        frame_str = str(frame) + eq_str + str(x) + ":" + str(y) + ":" + str(x_scale) + ":" + str(y_scale) + ":" + str(rotation) + ":" + str(opacity)
        value += frame_str + ";"

    ep.value = value.strip(";")

    return ep

def _create_region_editor(clip, editable_properties):
    aligned = [ep for ep in editable_properties if ep.name == "composite.aligned"][0]
    distort = [ep for ep in editable_properties if ep.name == "composite.distort"][0]
    operator = [ep for ep in editable_properties if ep.name == "composite.operator"][0]
    values = ["over","and","or","xor"]
    deinterlace = [ep for ep in editable_properties if ep.name == "composite.deinterlace"][0]
    progressive = [ep for ep in editable_properties if ep.name == "composite.progressive"][0]
    force_values = [_("Nothing"),_("Progressive"),_("Deinterlace"),_("Both")]

    combo_box = Gtk.ComboBoxText()
    for val in force_values:
        combo_box.append_text(val)
    selection = _get_force_combo_index(deinterlace, progressive)
    combo_box.set_active(selection)
    combo_box.connect("changed", _compositor_editor_force_combo_box_callback, (deinterlace, progressive))
    force_vbox = Gtk.VBox(False, 4)
    force_vbox.pack_start(Gtk.Label(label=_("Force")), True, True, 0)
    force_vbox.pack_start(combo_box, True, True, 0)

    hbox = Gtk.HBox(False, 4)
    hbox.pack_start(guiutils.get_pad_label(3, 5), False, False, 0)
    hbox.pack_start(_get_boolean_check_box_button_column(_("Align"), aligned), False, False, 0)
    hbox.pack_start(_get_boolean_check_box_button_column(_("Distort"), distort), False, False, 0)
    # THESE ARE DISABLED BECAUSE CHANGING ALPHA MODE CAN MAKE PROJECTS UNOPENABLE IF THE AFFECTED 
    # COMPOSITOR IS ON THE FIRST FRAME
    #hbox.pack_start(Gtk.Label(), True, True, 0)
    #hbox.pack_start(_get_combo_box_column(_("Alpha"), values, operator), False, False, 0)
    hbox.pack_start(Gtk.Label(), True, True, 0)
    hbox.pack_start(force_vbox, False, False, 0)
    hbox.pack_start(guiutils.get_pad_label(3, 5), False, False, 0)
    return hbox

def _create_color_grader(filt, editable_properties, editor_name, track, clip_index):
    color_grader = extraeditors.ColorGrader(editable_properties)

    vbox = Gtk.VBox(False, 4)
    vbox.pack_start(Gtk.Label(), True, True, 0)
    vbox.pack_start(color_grader.widget, False, False, 0)
    vbox.pack_start(Gtk.Label(), True, True, 0)
    vbox.no_separator = True
    return vbox

def _get_filter_rect_geom_editor(ep):
    return keyframeeditor.FilterRectGeometryEditor(ep)

def _get_no_kf_rect_geom_editor(ep):
    return keyframeeditor.GeometryNoKeyframes(ep)

def _create_crcurves_editor(filt, editable_properties, editor_name, track, clip_index):
    curves_editor = extraeditors.CatmullRomFilterEditor(editable_properties)

    vbox = Gtk.VBox(False, 4)
    vbox.pack_start(curves_editor.widget, False, False, 0)
    vbox.pack_start(Gtk.Label(), True, True, 0)
    vbox.no_separator = True
    return vbox

def _create_filter_roto_geom_editor(filt, editable_properties, editor_name, track, clip_index):
    clip, filter_index, prop, property_index, args_str = editable_properties[0].used_create_params

    kf_editable_property = propertyedit.KeyFrameFilterRotatingGeometryProperty(
                                editable_properties[0].used_create_params, 
                                editable_properties,
                                track, 
                                clip_index)

    kf_edit_geom_editor = keyframeeditor.FilterRotatingGeometryEditor(kf_editable_property)

    vbox = Gtk.VBox(False, 4)
    vbox.pack_start(kf_edit_geom_editor, False, False, 0)
    vbox.pack_start(Gtk.Label(), True, True, 0)
    vbox.no_separator = True
    vbox.kf_edit_geom_editor = kf_edit_geom_editor
    return vbox

def _create_gradient_tint_editor(filt, editable_properties, editor_name, track, clip_index):
    clip, filter_index, prop, property_index, args_str = editable_properties[0].used_create_params

    kf_editable_property = propertyedit.GradientTintExtraEditorProperty(
                                editable_properties[0].used_create_params, 
                                editable_properties,
                                track, 
                                clip_index)

    kf_edit_geom_editor = keyframeeditor.GradientTintGeometryEditor(kf_editable_property)
    kf_edit_geom_editor.set_margin_bottom(4)

    vbox = Gtk.VBox(False, 4)
    vbox.pack_start(kf_edit_geom_editor, False, False, 0)
    vbox.no_separator = True
    vbox.kf_edit_geom_editor = kf_edit_geom_editor
    return vbox

def _create_crop_editor(filt, editable_properties, editor_name, track, clip_index):
    clip, filter_index, prop, property_index, args_str = editable_properties[0].used_create_params

    kf_editable_property = propertyedit.CropEditorProperty(
                                editable_properties[0].used_create_params, 
                                editable_properties,
                                track, 
                                clip_index)

    kf_edit_geom_editor = keyframeeditor.CropGeometryEditor(kf_editable_property)
    kf_edit_geom_editor.set_margin_bottom(4)

    vbox = Gtk.VBox(False, 4)
    vbox.pack_start(kf_edit_geom_editor, False, False, 0)
    vbox.no_separator = True
    vbox.kf_edit_geom_editor = kf_edit_geom_editor
    return vbox

def _create_alpha_shape_editor(filt, editable_properties, editor_name, track, clip_index):
    clip, filter_index, prop, property_index, args_str = editable_properties[0].used_create_params

    kf_editable_property = propertyedit.AlphaShapeRotatingGeometryProperty(
                                editable_properties[0].used_create_params, 
                                editable_properties,
                                track, 
                                clip_index)

    kf_edit_geom_editor = keyframeeditor.AlphaShapeGeometryEditor(kf_editable_property)
    kf_edit_geom_editor.set_margin_bottom(4)

    vbox = Gtk.VBox(False, 4)
    vbox.pack_start(kf_edit_geom_editor, False, False, 0)
    vbox.no_separator = True
    vbox.kf_edit_geom_editor = kf_edit_geom_editor
    return vbox

def _create_colorbox_editor(filt, editable_properties, editor_name, track, clip_index):
    colorbox_editor = extraeditors.ColorBoxFilterEditor(editable_properties)
    
    vbox = Gtk.VBox(False, 4)
    vbox.pack_start(colorbox_editor.widget, False, False, 0)
    vbox.pack_start(Gtk.Label(), True, True, 0)
    vbox.no_separator = True
    return vbox

def _create_anylaze_stabile_editor(filt, editable_properties, editor_name, track, clip_index):
    analyze_editor = extraeditors.AnalyzeStabilizeFilterEditor(filt, editable_properties)
    
    hbox = Gtk.HBox(False, 4)
    hbox.pack_start(Gtk.Label(), True, True, 0)
    hbox.pack_start(analyze_editor.widget, False, False, 0)
    hbox.no_separator = True
    return hbox

def _create_anylaze_motion_editor(filt, editable_properties, editor_name, track, clip_index):
    analyze_editor = extraeditors.AnalyzeMotionTrackingFilterEditor(filt, editable_properties)
    
    hbox = Gtk.HBox(False, 4)
    hbox.pack_start(Gtk.Label(), True, True, 0)
    hbox.pack_start(analyze_editor.widget, False, False, 0)
    hbox.no_separator = True
    return hbox

def _create_apply_motion_editor(filt, editable_properties, editor_name, track, clip_index):
    filter_index = editable_properties[0].filter_index
    clip = editable_properties[0].clip
    non_mlt_properties = propertyedit.get_non_mlt_editable_properties(clip, filt, filter_index, track, clip_index)
    xoff_prop = [ep for ep in non_mlt_properties if ep.name == "xoff"][0]
    xoff_prop.write_adjustment_values = True
    xoff_prop_editor = get_non_mlt_property_editor_row(xoff_prop, LADSPA_SLIDER)
    yoff_prop = [ep for ep in non_mlt_properties if ep.name == "yoff"][0]
    yoff_prop.write_adjustment_values = True
    yoff_prop_editor = get_non_mlt_property_editor_row(yoff_prop, LADSPA_SLIDER)
    interpretation_prop = [ep for ep in non_mlt_properties if ep.name == "interpretation"][0]
    interpretation_prop_editor = get_non_mlt_property_editor_row(interpretation_prop, COMBO_BOX)
    size_prop = [ep for ep in non_mlt_properties if ep.name == "size"][0]
    size_prop_editor = get_non_mlt_property_editor_row(size_prop, COMBO_BOX)
    
    editor = extraeditors.ApplyMotionTrackingFilterEditor(filt, editable_properties, [interpretation_prop_editor, xoff_prop_editor, yoff_prop_editor, size_prop_editor], non_mlt_properties)
    hbox = Gtk.HBox(False, 4)
    hbox.pack_start(editor.widget, True, True, 0)

    return hbox

def _create_apply_filter_mask_motion_editor(filt, editable_properties, editor_name, track, clip_index):
    filter_index = editable_properties[0].filter_index
    clip = editable_properties[0].clip
    non_mlt_properties = propertyedit.get_non_mlt_editable_properties(clip, filt, filter_index, track, clip_index)
    xoff_prop = [ep for ep in non_mlt_properties if ep.name == "xoff"][0]
    xoff_prop.write_adjustment_values = True
    xoff_prop_editor = get_non_mlt_property_editor_row(xoff_prop, LADSPA_SLIDER)
    yoff_prop = [ep for ep in non_mlt_properties if ep.name == "yoff"][0]
    yoff_prop.write_adjustment_values = True
    yoff_prop_editor = get_non_mlt_property_editor_row(yoff_prop, LADSPA_SLIDER)
    scale_prop = [ep for ep in non_mlt_properties if ep.name == "scale"][0]
    scale_prop.write_adjustment_values = True
    scale_prop_editor = get_non_mlt_property_editor_row(scale_prop, LADSPA_SLIDER)
    
    editor = extraeditors.FilterMaskApplyMotionTrackingEditor(filt, editable_properties, [xoff_prop_editor, yoff_prop_editor, scale_prop_editor], non_mlt_properties)
    hbox = Gtk.HBox(False, 4)
    hbox.pack_start(editor.widget, True, True, 0)

    return hbox

def _create_color_lgg_editor(filt, editable_properties, editor_name, track, clip_index):
    color_lgg_editor = extraeditors.ColorLGGFilterEditor(editable_properties)
    vbox = Gtk.VBox(False, 4)
    vbox.pack_start(color_lgg_editor.widget, False, False, 0)
    vbox.pack_start(Gtk.Label(), True, True, 0)
    vbox.no_separator = True
    return vbox

def _create_rotomask_editor(filt, editable_properties, editor_name, track, clip_index):

    property_editor_widgets_create_func = lambda: _create_rotomask_property_editor_widgets(editable_properties)

    kf_json_prop = [ep for ep in editable_properties if ep.name == "spline"][0]
    kf_editor = keyframeeditor.RotoMaskKeyFrameEditor(kf_json_prop, propertyparse.rotomask_json_value_string_to_kf_array)

    kfs_value_label = Gtk.Label(label=str(len(kf_editor.clip_editor.keyframes)))

    kf_row = guiutils.get_left_justified_box([guiutils.pad_label(12, 12), guiutils.bold_label(_("Keyframes") + ": "), kfs_value_label])
    
    kf, curve_points, kf_type = kf_editor.clip_editor.keyframes[0]
    curve_points_value_label = Gtk.Label(label=str(len(curve_points)))
    cps_row = guiutils.get_left_justified_box([guiutils.pad_label(12, 12), guiutils.bold_label(_("Curve Points") + ": "), curve_points_value_label])

    value_labels = [kfs_value_label, curve_points_value_label]

    lauch_button = Gtk.Button(label=_("Launch RotoMask editor"))
    lauch_button.connect("clicked", lambda b:_roto_lauch_pressed(filt, editable_properties, property_editor_widgets_create_func, value_labels))
    
    vbox = Gtk.VBox(False, 4)
    vbox.pack_start(guiutils.bold_label(_("RotoMask info")), False, False, 0)
    vbox.pack_start(kf_row, False, False, 0)
    vbox.pack_start(cps_row, False, False, 0)
    vbox.pack_start(guiutils.pad_label(12, 12), False, False, 0)
    vbox.pack_start(lauch_button, False, False, 0)
    vbox.pack_start(Gtk.Label(), True, True, 0)
    vbox.no_separator = True
    return vbox

def _create_infotips_editor(filt, editable_properties, editor_name, track, clip_index):
    
    args_str = filt.info.extra_editors_args[editor_name]
    args = propertyparse.args_string_to_args_dict(args_str)
    header_name = args["header"].replace("!", " ")
    link_text = _("Info & tips available under heading '{}'").format(header_name)     
    uri = "file://" + respaths.INFO_TIPS_DOC

    infotips_editor = extraeditors.InfoAndTipsEditor(uri, link_text)

    hbox = Gtk.VBox(False, 4)
    hbox.pack_start(infotips_editor.widget, False, False, 0)
    hbox.pack_start(Gtk.Label(), True, True, 0)
    hbox.no_separator = False
    return hbox

def _roto_lauch_pressed(filt, editable_properties, property_editor_widgets_create_func, value_labels):
    callbackbridge.rotomask_show_rotomask(filt, editable_properties, property_editor_widgets_create_func, value_labels)

def _create_rotomask_property_editor_widgets(editable_properties):
    # NOTE: EditanbleParam objects for are usually created in  propertyedit.get_filter_editable_properties(), this a deviation from normal pipeline
    # that was needed because RotoMask editor is a separate window.
    property_editor_widgets = []
    
    invert_prop = [ep for ep in editable_properties if ep.name == "invert"][0]
    invert_prop.args[propertyedit.DISPLAY_NAME] = translations.param_names["Invert"] # NOTE: We needed to put this here because we didn't use the normal method create these ( propertyedit.get_filter_editable_properties() )
    invert_editor =  _get_boolean_check_box_row(invert_prop, True)
    invert_editor.set_size_request(130, 20)

    feather_prop = [ep for ep in editable_properties if ep.name == "feather"][0]
    feather_prop.args[propertyedit.DISPLAY_NAME] = translations.param_names["Feather"] # NOTE: We needed to put this here because we didn't use the normal method create these ( propertyedit.get_filter_editable_properties() )
    feather_editor = _get_no_kf_slider_row(feather_prop, slider_name=None, compact=True)
    feather_editor.set_size_request(450, 20)

    feather_passes_prop = [ep for ep in editable_properties if ep.name == "feather_passes"][0]
    feather_passes_prop.args[propertyedit.DISPLAY_NAME] = translations.param_names["Feather Passes"] # NOTE: We needed to put this here because we didn't use the normal method create these ( propertyedit.get_filter_editable_properties() )
    feather_passes_editor = _get_no_kf_slider_row(feather_passes_prop, slider_name=None, compact=True)
    feather_passes_editor.set_size_request(450, 20)
    
    alpha_operation_prop = [ep for ep in editable_properties if ep.name == "alpha_operation"][0]
    alpha_operation_prop.args[propertyedit.DISPLAY_NAME] = translations.param_names["Alpha Mode"] # NOTE: We needed to put this here because we didn't use the normal method create these ( propertyedit.get_filter_editable_properties() )
    alpha_operation_editor = _get_combo_box_row(alpha_operation_prop, True)
    alpha_operation_editor.set_size_request(270, 20)
    
    mode_prop = [ep for ep in editable_properties if ep.name == "mode"][0]
    mode_prop.args[propertyedit.DISPLAY_NAME] = translations.param_names["Mode"] # NOTE: We needed to put this here because we didn't use the normal method create these ( propertyedit.get_filter_editable_properties() )
    mode_editor = _get_combo_box_row(mode_prop, True)
    mode_editor.set_size_request(270, 20)

    property_editor_widgets.append(invert_editor)
    property_editor_widgets.append(feather_editor)
    property_editor_widgets.append(feather_passes_editor)
    property_editor_widgets.append(alpha_operation_editor)
    property_editor_widgets.append(mode_editor)

    return property_editor_widgets

def _get_force_combo_index(deinterlace, progressive):
    # These correspond to hardcoded values ["Nothing","Progressive","Deinterlace","Both"] above
    if int(deinterlace.value) == 0:
        if int(progressive.value) == 0:
            return 0
        else:
            return 1
    else:
        if int(progressive.value) == 0:
            return 2
        else:
            return 3

def _get_keyframe_editor(editable_property):
    return keyframeeditor.KeyFrameEditor(editable_property)

def _get_keyframe_editor_clip(editable_property):
    return keyframeeditor.KeyFrameEditor(editable_property, False)

def _get_keyframe_editor_clip_fade(editable_property):
    return keyframeeditor.KeyFrameEditorClipFade(editable_property)

def _get_keyframe_editor_clip_fade_filter(editable_property):
    return keyframeeditor.KeyFrameEditorClipFadeFilter(editable_property)
 
def _get_keyframe_editor_release(editable_property):
    editor = keyframeeditor.KeyFrameEditor(editable_property)
    editor.connect_to_update_on_release()
    return editor
    
def _get_geometry_editor(editable_property):
    return keyframeeditor.GeometryEditor(editable_property, False)

def _get_no_editor():
    return None

def _set_digits(editable_property, scale, spin):
    try:
        digits_str = editable_property.args[SCALE_DIGITS]
        digits = int(digits_str)
    except:
        return

    scale.set_digits(digits)
    spin.set_digits(digits)

# -------------------------------------------------------- gui utils funcs
def _get_boolean_check_box_button_column(name, editable_property):
    check_button = Gtk.CheckButton()
    check_button.set_active(editable_property.value == "1")
    check_button.connect("toggled", editable_property.boolean_button_toggled)
    vbox = Gtk.VBox(False, 0)
    vbox.pack_start(Gtk.Label(label=name), True, True, 0)
    vbox.pack_start(check_button, True, True, 0)
    return vbox

def _get_combo_box_column(name, values, editable_property):
    combo_box = Gtk.ComboBoxText()
    for val in values:
        val = translations.get_combo_option(val)
        combo_box.append_text(val)
    
    # Set initial value
    selection = values.index(editable_property.value)
    combo_box.set_active(selection)    
    combo_box.connect("changed", editable_property.combo_selection_changed, values)

    vbox = Gtk.VBox(False, 4)
    vbox.pack_start(Gtk.Label(label=name), True, True, 0)
    vbox.pack_start(combo_box, True, True, 0)
    return vbox
    
# ------------------------------------ SPECIAL VALUE UPDATE METHODS
# LADSPA filters do not respond to MLT property updates and 
# need to be recreated to update output
def _ladspa_spinner_update(editable_property, spinner, adjustment):
    try:
        # spin and slider use same adjustment and we seem to be get unchanged value 
        # on enter press, so we are using SpinButton text to get changed value.
        value = float(spinner.get_text())
        adjustment.set_value(value)
        _ladspa_slider_update(editable_property, adjustment)
    except:
        pass # text is not number. do nothing

def _ladspa_slider_update(editable_property, adjustment):
    # ...or segfault
    PLAYER().stop_playback()
    
    # Change property value
    editable_property.adjustment_value_changed(adjustment)
    
    # Update output by cloning and replacing filter
    ladspa_filter = editable_property._get_filter_object()
    filter_clone = mltfilters.clone_filter_object(ladspa_filter, PROJECT().profile)
    clip = editable_property.track.clips[editable_property.clip_index]

    mltfilters.detach_all_filters(clip)
    clip.filters.pop(editable_property.filter_index)
    clip.filters.insert(editable_property.filter_index, filter_clone)
    mltfilters.attach_all_filters(clip)

def _clip_frame_slider_update(editable_property, adjustment):
    PLAYER().stop_playback()
    editable_property.adjustment_value_changed(adjustment)

# editor types -> creator functions
EDITOR_ROW_CREATORS = { \
    SLIDER:lambda ep :_get_slider_row(ep),
    BOOLEAN_CHECK_BOX:lambda ep :_get_boolean_check_box_row(ep),
    COMBO_BOX:lambda ep :_get_combo_box_row(ep),
    KEYFRAME_EDITOR: lambda ep : _get_keyframe_editor(ep),
    KEYFRAME_EDITOR_CLIP: lambda ep : _get_keyframe_editor_clip(ep),
    KEYFRAME_EDITOR_CLIP_FADE: lambda ep : _get_keyframe_editor_clip_fade(ep),
    KEYFRAME_EDITOR_CLIP_FADE_FILTER: lambda ep : _get_keyframe_editor_clip_fade_filter(ep),
    KEYFRAME_EDITOR_RELEASE: lambda ep : _get_keyframe_editor_release(ep),
    GEOMETRY_EDITOR: lambda ep : _get_geometry_editor(ep),
    COLOR_SELECT: lambda ep: _get_color_selector(ep),
    FILTER_WIPE_SELECT:  lambda ep: _get_filter_wipe_selector(ep),
    LADSPA_SLIDER: lambda ep: _get_ladspa_slider_row(ep),
    CLIP_FRAME_SLIDER: lambda ep: _get_clip_frame_slider(ep),
    FILE_SELECTOR: lambda ep: _get_file_select_editor(ep),
    FADE_LENGTH: lambda ep: _get_fade_length_editor(ep),
    NO_EDITOR: lambda ep: _get_no_editor(),
    COMPOSITE_EDITOR_BUILDER: lambda comp, editable_properties: _create_composite_editor(comp, editable_properties),
    REGION_EDITOR_BUILDER: lambda comp, editable_properties: _create_region_editor(comp, editable_properties),
    ROTATION_GEOMETRY_EDITOR_BUILDER: lambda comp, editable_properties: _create_rotion_geometry_editor(comp, editable_properties),
    COLOR_CORRECTOR: lambda filt, editable_properties, editor_name, track, clip_index: \
                                _create_color_grader(filt, editable_properties, editor_name, track, clip_index),
    CR_CURVES: lambda filt, editable_properties, editor_name, track, clip_index: \
                                _create_crcurves_editor(filt, editable_properties, editor_name, track, clip_index),
    COLOR_BOX: lambda filt, editable_properties, editor_name, track, clip_index: \
                                _create_colorbox_editor(filt, editable_properties, editor_name, track, clip_index),
    COLOR_LGG: lambda filt, editable_properties, editor_name, track, clip_index: \
                                _create_color_lgg_editor(filt, editable_properties, editor_name, track, clip_index),
    ROTOMASK: lambda filt, editable_properties, editor_name, track, clip_index: \
                                _create_rotomask_editor(filt, editable_properties, editor_name, track, clip_index),
    FILTER_ROTATION_GEOM_EDITOR: lambda filt, editable_properties, editor_name, track, clip_index: \
                                _create_filter_roto_geom_editor(filt, editable_properties,  editor_name, track, clip_index),
    INFOANDTIPS: lambda filt, editable_properties, editor_name, track, clip_index: \
                                _create_infotips_editor(filt, editable_properties, editor_name, track, clip_index),
    ANALYZE_STABILIZE: lambda filt, editable_properties, editor_name, track, clip_index: \
                                _create_anylaze_stabile_editor(filt, editable_properties, editor_name, track, clip_index),
    ANALYZE_MOTION: lambda filt, editable_properties, editor_name, track, clip_index: \
                                _create_anylaze_motion_editor(filt, editable_properties, editor_name, track, clip_index),
    APPLY_MOTION: lambda filt, editable_properties, editor_name, track, clip_index: \
                                _create_apply_motion_editor(filt, editable_properties, editor_name, track, clip_index),
    APPLY_FILTER_MASK_MOTION: lambda filt, editable_properties, editor_name, track, clip_index: \
                                _create_apply_filter_mask_motion_editor(filt, editable_properties, editor_name, track, clip_index),
    TEXT_ENTRY: lambda ep: _get_text_entry(ep),
    NO_KF_RECT: lambda ep : _get_no_kf_rect_geom_editor(ep),
    FILTER_RECT_GEOM_EDITOR: lambda ep : _get_filter_rect_geom_editor(ep),
    GRADIENT_TINT:  lambda filt, editable_properties, editor_name, track, clip_index: \
                                _create_gradient_tint_editor(filt, editable_properties, editor_name, track, clip_index),
    CROP_EDITOR:  lambda filt, editable_properties, editor_name, track, clip_index: \
                                _create_crop_editor(filt, editable_properties, editor_name, track, clip_index),
    ALPHA_SHAPE_EDITOR:  lambda filt, editable_properties, editor_name, track, clip_index: \
                                _create_alpha_shape_editor(filt, editable_properties, editor_name, track, clip_index) 
    }

