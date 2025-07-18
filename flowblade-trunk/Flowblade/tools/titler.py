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
import array
import cairo
import copy
import hashlib
import os
import pickle
from PIL import Image, ImageFilter
import threading
import time

from gi.repository import Gtk, Gdk, GdkPixbuf
from gi.repository import GLib, GObject
from gi.repository import Pango
from gi.repository import PangoCairo

import atomicfile
import toolsdialogs
from editorstate import PLAYER
import editorstate
import gui
import guicomponents
import guiutils
import gtkbuilder
import gtkevents
import dialogutils
import projectaction
import respaths
import positionbar
import utils
import vieweditor
import vieweditorlayer
import userfolders

_titler = None
_titler_data = None
_titler_lastdir = None

_clip_data = None

_keep_titler_data = True

_filling_layer_list = False

VIEW_EDITOR_WIDTH = 815
VIEW_EDITOR_HEIGHT = 620

TEXT_LAYER_LIST_WIDTH = 300
TEXT_LAYER_LIST_HEIGHT = 150

TEXT_VIEW_WIDTH = 300
TEXT_VIEW_HEIGHT = 200

DEFAULT_FONT_SIZE = 25

FACE_REGULAR = "Regular"
FACE_BOLD = "Bold"
FACE_ITALIC = "Italic"
FACE_BOLD_ITALIC = "Bold Italic"

DEFAULT_FONT_SIZE = 40

ALIGN_LEFT = 0
ALIGN_CENTER = 1
ALIGN_RIGHT = 2

VERTICAL = 0
HORIZONTAL = 1

def show_titler():
    global _titler_data, _clip_data
    if _titler_data == None:
        _titler_data = TitlerData()

    _clip_data = None

    global _titler
    if _titler != None:
        primary_txt = _("Titler is already open")
        secondary_txt =  _("Only single instance of Titler can be opened.")
        dialogutils.info_message(primary_txt, secondary_txt, gui.editor_window.window)
        return

    _titler = Titler()
    _titler.load_titler_data()
    _titler.show_current_frame()

def edit_tline_title(clip, track, callback):
    global _titler
    if _titler != None:
        primary_txt = _("Titler is already open")
        secondary_txt =  _("Only single instance of Titler can be opened.")
        dialogutils.info_message(primary_txt, secondary_txt, gui.editor_window.window)
        return
        
    global _titler_data, _clip_data
    _titler_data = copy.deepcopy(clip.titler_data)
    _clip_data = (clip, track, callback)

    _titler = Titler()
    _titler.load_titler_data()
    _titler.show_current_frame()

def _edit_title_exit(new_title_path):
    # We need to do this in particular way to get file handle of the created png
    # released for MLT producer creation, e.g clean_titler_instance() function below.
    global _titler_data

    new_clip_titler_data = _titler_data
    _titler_data = None
    _titler.set_visible(False)
    _titler.destroy()

    GLib.idle_add(_do_title_edit_callback, new_title_path, new_clip_titler_data)

def _do_title_edit_callback(new_title_path, new_clip_titler_data):

    global _clip_data
    clip, track, callback = _clip_data
    _clip_data = None

    callback(clip, track, new_title_path, new_clip_titler_data)
    
def close_titler():
    global _titler, _titler_data
    
    _titler.set_visible(False)
    _titler.destroy()

    GLib.idle_add(titler_destroy)

def titler_destroy():
    global _titler, _titler_data

    _titler = None

    if not _keep_titler_data:
        _titler_data = None

def reset_titler():
    global _titler, _keep_titler_data, _titler_data

    if _titler != None:
        temp_keep_val = _keep_titler_data
        _keep_titler_data = True
        titler_destroy()
        _keep_titler_data = temp_keep_val
        show_titler()
    else:
        _titler_data = None

def clean_titler_instance():
    global _titler
    _titler = None

# ------------------------------------------------------------- data
class TextLayer:
    """
    Data needed to create a pango text layout.
    """
    def __init__(self):
        self.text = "Text"
        self.x = 0.0
        self.y = 0.0
        self.angle = 0.0 # future feature
        self.font_family = "Times New Roman"
        self.font_face = FACE_REGULAR
        self.font_size = DEFAULT_FONT_SIZE
        self.fill_on = True
        self.color_rgba = (1.0, 1.0, 1.0, 1.0) 
        self.alignment = ALIGN_LEFT
        self.pixel_size = (100, 100)
        self.spacing = 5

        self.gradient_color_rgba = None
        self.gradient_direction = VERTICAL

        self.outline_on = False
        self.outline_color_rgba = (0.3, 0.3, 0.3, 1.0) 
        self.outline_width = 2

        self.shadow_on = False
        self.shadow_color_rgb = (0.0, 0.0, 0.0) 
        self.shadow_opacity = 100
        self.shadow_xoff = 3
        self.shadow_yoff = 3
        self.shadow_blur = 0.0
        
        self.pango_layout = None # PangoTextLayout object

        self.layer_attributes = None # future feature 
        self.visible = True

    def get_font_desc_str(self):
        return self.font_family + " " + self.font_face + " " + str(self.font_size)

    def update_pango_layout(self):
        self.pango_layout.load_layer_data(self)


class TitlerData:
    """
    Data edited in titler editor
    """
    def __init__(self):
        self.layers = []
        self.active_layer = None
        self.add_layer()
        self.scroll_params = None # future feature
        
    def add_layer(self):
        # adding layer makes new layer active
        self.active_layer = TextLayer()
        self.active_layer.pango_layout = PangoTextLayout(self.active_layer)
        self.layers.append(self.active_layer)

    def get_active_layer_index(self):
        return self.layers.index(self.active_layer)
    
    def save(self, save_file_path):
        save_data = copy.copy(self)
        save_data.destroy_pango_layouts()
        with atomicfile.AtomicFileWriter(save_file_path, "wb") as afw:
            write_file = afw.get_file()
            pickle.dump(save_data, write_file)
        self.create_pango_layouts() # we just destroyed these because they don't pickle, they need to be recreated.

    def create_pango_layouts(self):
        for layer in self.layers:
            layer.pango_layout = PangoTextLayout(layer)

    def destroy_pango_layouts(self):
        for layer in self.layers:
            layer.pango_layout = None
                
    def data_compatibility_update(self):
        # We added new stuff for 2.8 and need to update data created with older versions.
        for layer in self.layers:
            if hasattr(layer, "gradient_color_rgba") == False:
                layer.gradient_color_rgba = None
                layer.gradient_direction = VERTICAL

# ---------------------------------------------------------- editor
class Titler(Gtk.Window):
    def __init__(self):
        GObject.GObject.__init__(self)
        self.set_title(_("Titler"))
        self.connect("delete-event", lambda w, e:close_titler())
        
        if editorstate.SCREEN_HEIGHT < 865:
            global TEXT_LAYER_LIST_HEIGHT, TEXT_VIEW_HEIGHT, VIEW_EDITOR_HEIGHT
            TEXT_LAYER_LIST_HEIGHT = 130
            TEXT_VIEW_HEIGHT = 130
            VIEW_EDITOR_HEIGHT = 350

        if editorstate.screen_size_small_height() == True:
            global VIEW_EDITOR_WIDTH
            VIEW_EDITOR_WIDTH = 680
            
        self.block_updates = False
        
        self.view_editor = vieweditor.ViewEditor(PLAYER().profile, VIEW_EDITOR_WIDTH, VIEW_EDITOR_HEIGHT)
        self.view_editor.active_layer_changed_listener = self.active_layer_changed
        
        self.guides_toggle = vieweditor.GuidesViewToggle(self.view_editor)
        
        add_b = Gtk.Button(label=_("Add"))
        del_b = Gtk.Button(label=_("Delete"))
        add_b.connect("clicked", lambda w:self._add_layer_pressed())
        del_b.connect("clicked", lambda w:self._del_layer_pressed())
        add_del_box = Gtk.HBox()
        add_del_box = Gtk.HBox(True,1)
        add_del_box.pack_start(add_b, True, True, 0)
        add_del_box.pack_start(del_b, True, True, 0)

        center_h = Gtk.Button()
        gtkbuilder.button_set_image(center_h, "center_horizontal")
        center_h.connect("clicked", lambda w:self._center_h_pressed())
        center_v = Gtk.Button()
        gtkbuilder.button_set_image(center_v, "center_vertical")
        center_v.connect("clicked", lambda w:self._center_v_pressed())

        self.layer_list = TextLayerListView(self._layer_selection_changed, self._layer_visibility_toggled)
        self.layer_list.set_size_request(TEXT_LAYER_LIST_WIDTH, TEXT_LAYER_LIST_HEIGHT)
    
        self.text_view = Gtk.TextView()
        self.text_view.set_pixels_above_lines(2)
        self.text_view.set_left_margin(2)
        self.text_view.get_buffer().connect("changed", self._text_changed)

        self.sw = Gtk.ScrolledWindow()
        self.sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.ALWAYS)
        self.sw.add(self.text_view)
        self.sw.set_size_request(TEXT_VIEW_WIDTH, TEXT_VIEW_HEIGHT)

        scroll_frame = Gtk.Frame()
        scroll_frame.add(self.sw)
        
        self.tc_display = guicomponents.MonitorTCDisplay()
        self.tc_display.use_internal_frame = True
        self.tc_display.widget.set_valign(Gtk.Align.CENTER)
        
        self.pos_bar = positionbar.PositionBar()
        self.pos_bar.set_listener(self.position_listener)
        self.pos_bar.update_display_from_producer(PLAYER().producer)
        self.pos_bar.mouse_release_listener = self.pos_bar_mouse_released

        pos_bar_frame = Gtk.HBox()
        pos_bar_frame.add(self.pos_bar.widget)
        pos_bar_frame.set_valign(Gtk.Align.CENTER)
                
        font_map = PangoCairo.font_map_get_default()
        unsorted_families = font_map.list_families()
        if len(unsorted_families) == 0:
            print("No font families found in system! Titler will not work.")
        self.font_families = sorted(unsorted_families, key=lambda family: family.get_name())
        self.font_family_indexes_for_name = {}
        combo = Gtk.ComboBoxText()
        indx = 0
        for family in self.font_families:
            combo.append_text(family.get_name())
            self.font_family_indexes_for_name[family.get_name()] = indx
            indx += 1
        combo.set_active(0)
        self.font_select = combo
        self.font_select.connect("changed", self._edit_value_changed)
        adj = Gtk.Adjustment(value=float(DEFAULT_FONT_SIZE), lower=float(1), upper=float(300), step_increment=float(1))
        self.size_spin = Gtk.SpinButton()
        self.size_spin.set_adjustment(adj)
        self.size_spin.connect("changed", self._edit_value_changed)
        self.spin_adapter = gtkevents.KeyPressEventAdapter(self.size_spin, self._key_pressed_on_widget)

        font_main_row = Gtk.HBox()
        font_main_row.pack_start(self.font_select, True, True, 0)
        font_main_row.pack_start(guiutils.pad_label(5, 5), False, False, 0)
        font_main_row.pack_start(self.size_spin, False, False, 0)
        guiutils.set_margins(font_main_row, 0,4,0,0)
        
        self.bold_font = Gtk.ToggleButton()
        self.italic_font = Gtk.ToggleButton()
        gtkbuilder.button_set_image_icon_name(self.bold_font, "format-text-bold")
        gtkbuilder.button_set_image_icon_name(self.italic_font, "format-text-italic")
        self.bold_font.connect("clicked", self._edit_value_changed)
        self.italic_font.connect("clicked", self._edit_value_changed)
        
        self.left_align = Gtk.RadioButton(None)
        self.center_align = Gtk.RadioButton.new_from_widget(self.left_align)
        self.right_align = Gtk.RadioButton.new_from_widget(self.left_align)
        gtkbuilder.button_set_image_icon_name(self.left_align, "format-justify-left")
        gtkbuilder.button_set_image_icon_name(self.center_align, "format-justify-center")
        gtkbuilder.button_set_image_icon_name(self.right_align, "format-justify-right")
        self.left_align.set_mode(False)
        self.center_align.set_mode(False)
        self.right_align.set_mode(False)
        self.left_align.connect("clicked", self._edit_value_changed)
        self.center_align.connect("clicked", self._edit_value_changed)
        self.right_align.connect("clicked", self._edit_value_changed)
        
        self.color_button = Gtk.ColorButton.new_with_rgba(Gdk.RGBA(red=1.0, green=1.0, blue=1.0, alpha=1.0))
        self.color_button.connect("color-set", self._edit_value_changed)
        self.fill_on = Gtk.CheckButton()
        self.fill_on.set_active(True)
        self.fill_on.connect("toggled", self._edit_value_changed)

        buttons_box = Gtk.HBox()
        buttons_box.pack_start(Gtk.Label(), True, True, 0)
        buttons_box.pack_start(self.bold_font, False, False, 0)
        buttons_box.pack_start(self.italic_font, False, False, 0)
        buttons_box.pack_start(guiutils.pad_label(5, 5), False, False, 0)
        buttons_box.pack_start(self.left_align, False, False, 0)
        buttons_box.pack_start(self.center_align, False, False, 0)
        buttons_box.pack_start(self.right_align, False, False, 0)
        buttons_box.pack_start(guiutils.pad_label(15, 5), False, False, 0)
        buttons_box.pack_start(self.color_button, False, False, 0)
        buttons_box.pack_start(guiutils.pad_label(2, 1), False, False, 0)
        buttons_box.pack_start(self.fill_on, False, False, 0)
        buttons_box.pack_start(Gtk.Label(), True, True, 0)

        # ------------------------------------------- Outline Panel
        outline_size = Gtk.Label(label=_("Size:"))
        
        self.out_line_color_button = Gtk.ColorButton.new_with_rgba(Gdk.RGBA(red=0.3, green=0.3, blue=0.3, alpha=1.0))
        self.out_line_color_button.connect("color-set", self._edit_value_changed)

        adj2 = Gtk.Adjustment(value=float(3), lower=float(1), upper=float(50), step_increment=float(1))
        self.out_line_size_spin = Gtk.SpinButton()
        self.out_line_size_spin.set_adjustment(adj2)
        self.out_line_size_spin.connect("changed", self._edit_value_changed)
        self.out_line_size_adapter = gtkevents.KeyPressEventAdapter(self.out_line_size_spin, self._key_pressed_on_widget)
        
        self.outline_on = Gtk.CheckButton()
        self.outline_on.set_active(False)
        self.outline_on.connect("toggled", self._edit_value_changed)
        
        outline_box = Gtk.HBox()
        outline_box.pack_start(outline_size, False, False, 0)
        outline_box.pack_start(guiutils.pad_label(2, 1), False, False, 0)
        outline_box.pack_start(self.out_line_size_spin, False, False, 0)
        outline_box.pack_start(guiutils.pad_label(15, 1), False, False, 0)
        outline_box.pack_start(self.out_line_color_button, False, False, 0)
        outline_box.pack_start(guiutils.pad_label(2, 1), False, False, 0)
        outline_box.pack_start(self.outline_on, False, False, 0)
        outline_box.pack_start(Gtk.Label(), True, True, 0)

        # -------------------------------------------- Shadow panel 
        shadow_opacity_label = Gtk.Label(label=_("Opacity:"))
        shadow_xoff = Gtk.Label(label=_("X Off:"))
        shadow_yoff = Gtk.Label(label=_("Y Off:"))
        shadow_blur_label = Gtk.Label(label=_("Blur:"))
        
        self.shadow_opa_spin = Gtk.SpinButton()
 
        adj3 = Gtk.Adjustment(value=float(100), lower=float(1), upper=float(100), step_increment=float(1))
        self.shadow_opa_spin.set_adjustment(adj3)
        self.shadow_opa_spin.connect("changed", self._edit_value_changed)
        self.shadow_opa_spin_adapter = gtkevents.KeyPressEventAdapter(self.shadow_opa_spin, self._key_pressed_on_widget)
        
        self.shadow_xoff_spin = Gtk.SpinButton()

        adj4 = Gtk.Adjustment(value=float(3), lower=float(1), upper=float(100), step_increment=float(1))
        self.shadow_xoff_spin.set_adjustment(adj4)
        self.shadow_xoff_spin.connect("changed", self._edit_value_changed)
        self.shadow_xoff_spin_adapter = gtkevents.KeyPressEventAdapter(self.shadow_xoff_spin, self._key_pressed_on_widget)
        
        self.shadow_yoff_spin = Gtk.SpinButton()

        adj5 = Gtk.Adjustment(value=float(3), lower=float(1), upper=float(100), step_increment=float(1))
        self.shadow_yoff_spin.set_adjustment(adj5)
        self.shadow_yoff_spin.connect("changed", self._edit_value_changed)
        self.shadow_yoff_spin_adapter = gtkevents.KeyPressEventAdapter(self.shadow_yoff_spin, self._key_pressed_on_widget)
        
        self.shadow_on = Gtk.CheckButton()
        self.shadow_on.set_active(False)
        self.shadow_on.connect("toggled", self._edit_value_changed)
        
        self.shadow_color_button = Gtk.ColorButton.new_with_rgba(Gdk.RGBA(red=0.3, green=0.3, blue=0.3, alpha=1.0))
        self.shadow_color_button.connect("color-set", self._edit_value_changed)

        self.shadow_blur_spin = Gtk.SpinButton()
        adj6 = Gtk.Adjustment(value=float(0), lower=float(0), upper=float(20), step_increment=float(1))
        self.shadow_blur_spin.set_adjustment(adj6)
        self.shadow_blur_spin.connect("changed", self._edit_value_changed)

        shadow_box_1 = Gtk.HBox()
        shadow_box_1.pack_start(shadow_opacity_label, False, False, 0)
        shadow_box_1.pack_start(self.shadow_opa_spin, False, False, 0)
        shadow_box_1.pack_start(guiutils.pad_label(15, 1), False, False, 0)
        shadow_box_1.pack_start(self.shadow_color_button, False, False, 0)
        shadow_box_1.pack_start(guiutils.pad_label(2, 1), False, False, 0)
        shadow_box_1.pack_start(self.shadow_on, False, False, 0)
        shadow_box_1.pack_start(Gtk.Label(), True, True, 0)
        guiutils.set_margins(shadow_box_1, 0,4,0,0)

        shadow_box_2 = Gtk.HBox()
        shadow_box_2.pack_start(shadow_xoff, False, False, 0)
        shadow_box_2.pack_start(self.shadow_xoff_spin, False, False, 0)
        shadow_box_2.pack_start(guiutils.pad_label(15, 1), False, False, 0)
        shadow_box_2.pack_start(shadow_yoff, False, False, 0)
        shadow_box_2.pack_start(self.shadow_yoff_spin, False, False, 0)
        shadow_box_2.pack_start(Gtk.Label(), True, True, 0)

        shadow_box_3 = Gtk.HBox()
        shadow_box_3.pack_start(shadow_blur_label, False, False, 0)
        shadow_box_3.pack_start(self.shadow_blur_spin, False, False, 0)
        shadow_box_3.pack_start(Gtk.Label(), True, True, 0)

        # ------------------------------------ Gradient panel
        self.gradient_color_button = Gtk.ColorButton.new_with_rgba(Gdk.RGBA(red=0.0, green=0.0, blue=0.8, alpha=1.0))
        self.gradient_color_button.connect("color-set", self._edit_value_changed)
        self.gradient_on = Gtk.CheckButton()
        self.gradient_on.set_active(True)
        self.gradient_on.connect("toggled", self._edit_value_changed)

        direction_label = Gtk.Label(label=_("Gradient Direction:"))
        self.direction_combo = Gtk.ComboBoxText()
        self.direction_combo.append_text(_("Vertical"))
        self.direction_combo.append_text(_("Horizontal"))
        self.direction_combo.set_active(0)
        self.direction_combo.connect("changed", self._edit_value_changed)
         
        gradient_box_row1 = Gtk.HBox()
        gradient_box_row1.pack_start(self.gradient_on, False, False, 0)
        gradient_box_row1.pack_start(self.gradient_color_button, False, False, 0)
        gradient_box_row1.pack_start(Gtk.Label(), True, True, 0)

        gradient_box_row2 = Gtk.HBox()
        gradient_box_row2.pack_start(direction_label, False, False, 0)
        gradient_box_row2.pack_start(self.direction_combo, False, False, 0)
        gradient_box_row2.pack_start(Gtk.Label(), True, True, 0)
        
        gradient_box = Gtk.VBox()
        gradient_box.pack_start(gradient_box_row1, False, False, 0)
        gradient_box.pack_start(gradient_box_row2, False, False, 0)
        gradient_box.pack_start(Gtk.Label(), True, True, 0)
                
        # ---------------------------------------------------- Save and Load buttons        
        load_layers = Gtk.Button(label=_("Load Layers"))
        load_layers.connect("clicked", lambda w:self._load_layers_pressed())
        save_layers = Gtk.Button(label=_("Save Layers"))
        save_layers.connect("clicked", lambda w:self._save_layers_pressed())
        clear_layers = Gtk.Button(label=_("Clear All"))
        clear_layers.connect("clicked", lambda w:self._clear_layers_pressed())

        layers_save_buttons_row = Gtk.HBox()
        layers_save_buttons_row.pack_start(Gtk.Label(), True, True, 0)
        layers_save_buttons_row.pack_start(save_layers, False, False, 0)
        layers_save_buttons_row.pack_start(load_layers, False, False, 0)
        layers_save_buttons_row.set_margin_right(4)
        layers_save_buttons_row.set_margin_top(2)
        
        # ---------------------------------------------------- X, Y pos input
        adj = Gtk.Adjustment(value=float(0), lower=float(0), upper=float(3000), step_increment=float(1))
        self.x_pos_spin = Gtk.SpinButton()
        self.x_pos_spin.set_adjustment(adj)
        self.x_pos_spin.connect("changed", self._position_value_changed)
        self.xpos_adapter = gtkevents.KeyPressEventAdapter(self.x_pos_spin, self._key_pressed_on_widget)
        
        adj = Gtk.Adjustment(value=float(0), lower=float(0), upper=float(3000), step_increment=float(1))
        self.y_pos_spin = Gtk.SpinButton()
        self.y_pos_spin.set_adjustment(adj)
        self.y_pos_spin.connect("changed", self._position_value_changed)
        self.y_pos_spin_adapter = gtkevents.KeyPressEventAdapter(self.y_pos_spin, self._key_pressed_on_widget)
        
        adj = Gtk.Adjustment(value=float(0), lower=float(0), upper=float(3000), step_increment=float(1))
        self.rotation_spin = Gtk.SpinButton()
        self.rotation_spin.set_adjustment(adj)
        self.rotation_spin.connect("changed", self._position_value_changed)
        self.rotation_spin_adapter = gtkevents.KeyPressEventAdapter(self.rotation_spin, self._key_pressed_on_widget)
        
        undo_pos = Gtk.Button()
        gtkbuilder.button_set_image_icon_name(undo_pos, "edit-undo")
        
        # ------------------------------------------------- Timeline controls
        prev_frame = Gtk.Button()
        gtkbuilder.button_set_image(prev_frame, "prev_frame_s")
        prev_frame.connect("clicked", lambda w:self._prev_frame_pressed())
        next_frame = Gtk.Button()
        gtkbuilder.button_set_image(next_frame, "next_frame_s")
        next_frame.connect("clicked", lambda w:self._next_frame_pressed())

        self.scale_selector = vieweditor.ScaleSelector(self)
        self.view_editor.scale_select = self.scale_selector

        # ------------------------------------------------------ Panels
        timeline_box = Gtk.HBox()
        timeline_box.pack_start(self.tc_display.widget, False, False, 0)
        timeline_box.pack_start(guiutils.pad_label(12, 12), False, False, 0)
        timeline_box.pack_start(pos_bar_frame, True, True, 0)
        timeline_box.pack_start(guiutils.pad_label(12, 12), False, False, 0)
        timeline_box.pack_start(prev_frame, False, False, 0)
        timeline_box.pack_start(next_frame, False, False, 0)
        timeline_box.pack_start(self.guides_toggle, False, False, 0)
        timeline_box.pack_start(self.scale_selector, False, False, 0)
        timeline_box.set_margin_top(6)
        timeline_box.set_margin_bottom(6)
        
        positions_box = Gtk.HBox()
        positions_box.pack_start(Gtk.Label(), True, True, 0)
        x_label = Gtk.Label(label="X:")
        x_label.set_margin_end(4)
        positions_box.pack_start(x_label, False, False, 0)
        positions_box.pack_start(self.x_pos_spin, False, False, 0)
        positions_box.pack_start(guiutils.pad_label(40, 5), False, False, 0)
        y_label = Gtk.Label(label="Y:")
        y_label.set_margin_end(4)
        positions_box.pack_start(y_label, False, False, 0)
        positions_box.pack_start(self.y_pos_spin, False, False, 0)
        positions_box.pack_start(guiutils.pad_label(40, 5), False, False, 0)
        positions_box.pack_start(center_h, False, False, 0)
        positions_box.pack_start(center_v, False, False, 0)
        positions_box.pack_start(Gtk.Label(), True, True, 0)

        controls_panel_1 = Gtk.VBox()
        controls_panel_1.pack_start(add_del_box, False, False, 0)
        controls_panel_1.pack_start(self.layer_list, True, True, 0)

        controls_panel_2 = Gtk.VBox()
        controls_panel_2.pack_start(font_main_row, False, False, 0)
        controls_panel_2.pack_start(buttons_box, False, False, 0)

        controls_panel_3 = Gtk.VBox()
        controls_panel_3.pack_start(outline_box, False, False, 0)

        controls_panel_4 = Gtk.VBox()
        controls_panel_4.pack_start(shadow_box_1, False, False, 0)
        controls_panel_4.pack_start(shadow_box_2, False, False, 0)
        controls_panel_4.pack_start(shadow_box_3, False, False, 0)

        controls_panel_5 = Gtk.VBox()
        controls_panel_5.pack_start(gradient_box, False, False, 0)

        notebook = Gtk.Notebook()
        notebook.append_page(guiutils.set_margins(controls_panel_2,8,8,8,8), Gtk.Label(label=_("Font")))
        notebook.append_page(guiutils.set_margins(controls_panel_3,8,8,8,8), Gtk.Label(label=_("Outline")))
        notebook.append_page(guiutils.set_margins(controls_panel_4,8,8,8,8), Gtk.Label(label=_("Shadow")))
        notebook.append_page(guiutils.set_margins(controls_panel_5,8,8,8,8), Gtk.Label(label=_("Gradient")))
        
        controls_panel = Gtk.VBox()
        controls_panel.pack_start(guiutils.get_named_frame(_("Layer Text"), scroll_frame), True, True, 0)
        controls_panel.pack_start(guiutils.set_margins(notebook, 0,0,10,4), False, False, 0)
        controls_panel.pack_start(guiutils.pad_label(1, 24), False, False, 0)
        controls_panel.pack_start(guiutils.get_named_frame(_("Layers"),controls_panel_1), True, True, 0)
        controls_panel.pack_start(layers_save_buttons_row, False, False, 0)
         
        view_editor_editor_buttons_row = Gtk.HBox()
        view_editor_editor_buttons_row.pack_start(positions_box, False, False, 0)
        view_editor_editor_buttons_row.pack_start(Gtk.Label(), True, True, 0)

        # ------------------------------------------------------- Editor buttons
        self.save_action_combo = Gtk.ComboBoxText()
        self.save_action_combo.append_text(_("Save As Title"))
        self.save_action_combo.append_text(_("Save As Graphic"))
        self.save_action_combo.set_active(0)

        exit_b = guiutils.get_sized_button(_("Close"), 150, 32)
        exit_b.connect("clicked", lambda w:close_titler())
        if _clip_data == None:
            save_text = _("Save Title")
        else:
            save_text = _("Update Title")
        
        save_titles_b = guiutils.get_sized_button(save_text, 150, 32)
        save_titles_b.connect("clicked", lambda w:self._save_title_pressed())
        
        self.info_text = Gtk.Label()
        
        editor_buttons_row = Gtk.HBox()
        editor_buttons_row.pack_start(self.info_text, True, True, 0)
        editor_buttons_row.pack_start(guiutils.pad_label(12, 2), False, False, 0)
        if _clip_data == None:
            editor_buttons_row.pack_start(self.save_action_combo, False, False, 0)
        editor_buttons_row.pack_start(guiutils.pad_label(32, 2), False, False, 0)
        editor_buttons_row.pack_start(exit_b, False, False, 0)
        editor_buttons_row.pack_start(save_titles_b, False, False, 0)
        
        # ------------------------------------------------------ window layout
        editor_panel = Gtk.VBox()
        editor_panel.pack_start(self.view_editor, True, True, 0)
        editor_panel.pack_start(timeline_box, False, False, 0)
        editor_panel.pack_start(guiutils.get_in_centering_alignment(view_editor_editor_buttons_row), False, False, 0)
        editor_panel.pack_start(guiutils.pad_label(2, 24), False, False, 0)
        editor_panel.pack_start(editor_buttons_row, False, False, 0)

        editor_row = Gtk.HBox()
        editor_row.pack_start(controls_panel, False, False, 0)
        editor_row.pack_start(editor_panel, True, True, 0)

        alignment = guiutils.set_margins(editor_row, 8,8,8,8)

        self.add(alignment)

        self.layer_list.fill_data_model()
        self._update_gui_with_active_layer_data()
        self.show_all()

        # -------------------------------------------------- window state listeners
        self.connect("size-allocate", lambda w, e:self.window_resized())
    
    def show_info(self, info_text):
        self.info_text.set_markup("<small>" + info_text + "</small>")
        #GLib.timeout_add(2500, self.clear_info)

    def clear_info(self):
        self.info_text.set_markup("")
        return False
        
    def load_titler_data(self):
        # clear and then load layers, and set layer 0 active
        self.view_editor.clear_layers()

        global _titler_data
        _titler_data.create_pango_layouts()

        for layer in _titler_data.layers:
            text_layer = vieweditorlayer.TextEditLayer(self.view_editor, layer.pango_layout)
            text_layer.mouse_released_listener  = self._editor_layer_mouse_released
            text_layer.set_rect_pos(layer.x, layer.y)
            text_layer.update_rect = True
            text_layer.visible = True
            self.view_editor.add_layer(text_layer)

        for layer in _titler_data.layers:
            layer.visible = True

        self._activate_layer(0)
        self.layer_list.fill_data_model()
        self.view_editor.edit_area.queue_draw()
        self._select_layer(0)
        
    def show_current_frame(self):
        frame = PLAYER().current_frame()
        length = PLAYER().producer.get_length()
        rgbdata = PLAYER().seek_and_get_rgb_frame(frame)
        self.view_editor.set_screen_rgb_data(rgbdata)
        self.pos_bar.set_normalized_pos(float(frame)/float(length))
        self.tc_display.set_frame(frame)
        self.pos_bar.widget.queue_draw()
        self._update_active_layout()

    def window_resized(self):
        scale = self.scale_selector.get_current_scale()
        self.scale_changed(scale)

    def scale_changed(self, new_scale):
        self.view_editor.set_scale_and_update(new_scale)
        self.view_editor.edit_area.queue_draw()

    def write_current_frame(self):
        self.view_editor.write_out_layers = True
        self.show_current_frame()

    def position_listener(self, normalized_pos, length):
        frame = normalized_pos * length
        self.tc_display.set_frame(int(frame))
        self.pos_bar.widget.queue_draw()

    def pos_bar_mouse_released(self, normalized_pos, length):
        frame = int(normalized_pos * length)
        PLAYER().seek_frame(frame)
        self.show_current_frame()

    def _save_title_pressed(self):
        global _titler_data, _clip_data

        if _clip_data != None:
            # Timeline title edit.
            md_str = hashlib.md5(str(os.urandom(32)).encode('utf-8')).hexdigest() + ".png"
            new_title_path = userfolders.get_render_dir() + md_str
            self.view_editor.write_callback = self.title_write_done
            self.view_editor.write_layers_to_png(new_title_path)
        else:
            if self.save_action_combo.get_active() == 1:
                toolsdialogs.save_titler_graphic_as_dialog(self._save_title_dialog_callback, "title.png", _titler_lastdir)
            else:
                dialog, entry = dialogutils.get_single_line_text_input_dialog(30, 130,
                                                            _("Select Title Name"),
                                                            _("Set Name"),
                                                            _("Title Name:"),
                                                            _("Title"))
                dialog.connect('response', self._titler_item_name_dialog_callback, entry)
                dialog.show_all()

    def title_write_done(self, new_title_path):
        GLib.idle_add(_edit_title_exit, new_title_path)
            
    def  _titler_item_name_dialog_callback(self, dialog, response_id, entry):
        if response_id == Gtk.ResponseType.ACCEPT:
            name = entry.get_text()
            dialog.destroy()
            
            if name == "":
                name = _("Title")
            
            md_str = hashlib.md5(str(os.urandom(32)).encode('utf-8')).hexdigest() + ".png"
            save_path = userfolders.get_render_dir() + md_str

            self.view_editor.write_layers_to_png(save_path)
            
            # Destroy pango layouts as they cannot be pickled and thus cannot be part of savefile where 
            # this data ends up as a clip.titler_data and mediafile.titler_data properties.
            # We need deep copy from picledable shallow copy so when pango layers get recreated
            # for titler they don't end up in save data.
            title_data_shallow = copy.copy(_titler_data)
            title_data_shallow.destroy_pango_layouts()
            title_data = copy.deepcopy(title_data_shallow)
 
            open_title_item_thread = OpenTitlerItemThread(name, save_path, title_data, self.view_editor)
            open_title_item_thread.start()
        else:
            dialog.destroy()

    def _save_title_dialog_callback(self, dialog, response_id):
        if response_id == Gtk.ResponseType.ACCEPT:
            try:
                filenames = dialog.get_filenames()
                dialog.destroy()
                save_path = filenames[0]
                self.view_editor.write_layers_to_png(save_path)
                (dirname, filename) = os.path.split(save_path)
                global _titler_lastdir
                _titler_lastdir = dirname

                #self.show_info(_("Saved Graphic."))
            
                open_file_thread = OpenFileThread(save_path, self.view_editor)
                open_file_thread.start()
                # INFOWINDOW
            except:
                # INFOWINDOW
                dialog.destroy()
                return
        else:
            dialog.destroy()

    def _save_layers_pressed(self):
        toolsdialogs.save_titler_data_as_dialog(self._save_layers_dialog_callback, "titler_layers", None)

    def _save_layers_dialog_callback(self, dialog, response_id):
        if response_id == Gtk.ResponseType.ACCEPT:
            filenames = dialog.get_filenames()
            save_path = filenames[0]
            _titler_data.save(save_path)
            dialog.destroy()
        else:
            dialog.destroy()
            
    def _load_layers_pressed(self):
        toolsdialogs.load_titler_data_dialog(self._load_layers_dialog_callback)
        
    def _load_layers_dialog_callback(self, dialog, response_id):
        if response_id == Gtk.ResponseType.ACCEPT:
            try:
                filenames = dialog.get_filenames()
                load_path = filenames[0]
                new_data = utils.unpickle(load_path)
                new_data.data_compatibility_update()
                global _titler_data
                _titler_data = new_data
                self.load_titler_data()
            except Exception as e:
                print("Titler._load_layers_dialog_callback", e)
                dialog.destroy()
                # INFOWINDOW
                return
                
            dialog.destroy()
        else:
            dialog.destroy()

    def _clear_layers_pressed(self):
        # INFOWINDOW
        # CONFIRM WINDOW HERE!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
        global _titler_data
        _titler_data = TitlerData()
        self.load_titler_data()

    def _keep_layers_toggled(self, widget):
        global _keep_titler_data
        _keep_titler_data = widget.get_active()

    def _key_pressed_on_widget(self, widget, event):
        # update layer for enter on size spin
        if widget == self.size_spin and event.keyval == Gdk.KEY_Return:
            self.size_spin.update()
            self._update_active_layout()
            return True

        # update layer for enter on x, y, angle
        if ((event.keyval == Gdk.KEY_Return) and ((widget == self.x_pos_spin) or
            (widget == self.y_pos_spin) or (widget == self.rotation_spin))):
            self.x_pos_spin.update()
            self.y_pos_spin.update()
            self.rotation_spin.update()
            _titler_data.active_layer.x = self.x_pos_spin.get_value()
            _titler_data.active_layer.y = self.y_pos_spin.get_value()
            self._update_editor_layer_pos()
            self.view_editor.edit_area.queue_draw()
            return True

        return False

    def _update_editor_layer_pos(self):
        shape = self.view_editor.active_layer.edit_point_shape
        shape.translate_points_to_pos(_titler_data.active_layer.x, 
                                      _titler_data.active_layer.y, 0)

    def _add_layer_pressed(self):
        global _titler_data
        _titler_data.add_layer()
        
        view_editor_layer = vieweditorlayer.TextEditLayer(self.view_editor, _titler_data.active_layer.pango_layout)
        view_editor_layer.mouse_released_listener  = self._editor_layer_mouse_released
        self.view_editor.edit_layers.append(view_editor_layer)
        
        layer_index = len(_titler_data.layers) - 1
        self.layer_list.fill_data_model()
        self._activate_layer(layer_index, True)
        self._select_layer(layer_index)
        
    def _del_layer_pressed(self):
        # we always need 1 layer
        if len(_titler_data.layers) < 2:
            return

        _titler_data.layers.remove(_titler_data.active_layer)
        self.view_editor.edit_layers.remove(self.view_editor.active_layer)
        self.layer_list.fill_data_model()
        self._activate_layer(0)
        self._select_layer(0)
        
    def _layer_visibility_toggled(self, layer_index):
        toggled_visible = (self.view_editor.edit_layers[layer_index].visible == False)
        self.view_editor.edit_layers[layer_index].visible = toggled_visible
        _titler_data.layers[layer_index].visible = toggled_visible
        self.layer_list.fill_data_model()

        self.view_editor.edit_area.queue_draw()
        
    def _center_h_pressed(self):
        # calculate top left x pos for centering
        w, h = _titler_data.active_layer.pango_layout.pixel_size
        centered_x = self.view_editor.profile_w/2 - w/2
        
        # update data and view
        _titler_data.active_layer.x = centered_x
        self._update_editor_layer_pos()
        self.view_editor.edit_area.queue_draw()
        
        self.block_updates = True
        self.x_pos_spin.set_value(centered_x)
        self.block_updates = False

    def _center_v_pressed(self):
        # calculate top left x pos for centering
        w, h = _titler_data.active_layer.pango_layout.pixel_size
        centered_y = self.view_editor.profile_h/2 - h/2
        
        # update data and view
        _titler_data.active_layer.y = centered_y
        self._update_editor_layer_pos()
        self.view_editor.edit_area.queue_draw()
        
        self.block_updates = True
        self.y_pos_spin.set_value(centered_y)
        self.block_updates = False

    def _prev_frame_pressed(self):
        PLAYER().seek_delta(-1)
        self.show_current_frame()

    def _next_frame_pressed(self):
        PLAYER().seek_delta(1)
        self.show_current_frame()

    def _layer_selection_changed(self, treeview, path, column):
        selected_row = path.get_indices()[0]

        # we're listening to "changed" on treeview and get some events (text updated)
        # when layer selection was not changed.
        if selected_row == -1:
            return

        self._activate_layer(selected_row)

    def active_layer_changed(self, layer_index):
        global _titler_data
        _titler_data.active_layer = _titler_data.layers[layer_index]
        self._update_gui_with_active_layer_data()
        _titler_data.active_layer.update_pango_layout()
        self._select_layer(layer_index)

    def _activate_layer(self, layer_index, is_new_layer=False):
        global _titler_data
        _titler_data.active_layer = _titler_data.layers[layer_index]
        
        if not is_new_layer:
            self._update_gui_with_active_layer_data() # Update GUI with layer data
        else:
            self._update_active_layout_font_properties() # Update layer font properties with current GUI values.
            self._update_gui_with_active_layer_data() # Update GUI with layer data
            
        _titler_data.active_layer.update_pango_layout()
        self.view_editor.activate_layer(layer_index)
        self.view_editor.active_layer.update_rect = True
        self.view_editor.edit_area.queue_draw()

    def _select_layer(self, layer_index):
        self.layer_list.treeview.get_selection().select_path(Gtk.TreePath.new_from_indices([layer_index]))
        self.layer_list.queue_draw()

    def _editor_layer_mouse_released(self):
        p = self.view_editor.active_layer.edit_point_shape.edit_points[0]
        
        self.block_updates = True

        self.x_pos_spin.set_value(p.x)
        self.y_pos_spin.set_value(p.y)
        
        _titler_data.active_layer.x = p.x
        _titler_data.active_layer.y = p.y

        self.block_updates = False

    def _text_changed(self, widget):
        self._update_active_layout()
        self._select_layer(_titler_data.get_active_layer_index())

    def _position_value_changed(self, widget):
        # mouse release when layer is moved causes this method to be called,
        # but we don't want to do any additional updates here for that event
        # This is only used when user presses arrows in position spins.
        if self.block_updates:
            return

        _titler_data.active_layer.x = self.x_pos_spin.get_value()
        _titler_data.active_layer.y = self.y_pos_spin.get_value()
        self._update_editor_layer_pos()
        self.view_editor.edit_area.queue_draw()

    def _edit_value_changed(self, widget):
        self._update_active_layout()

    def _update_active_layout(self):
        if self.block_updates:
            return

        global _titler_data
        buf = self.text_view.get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), include_hidden_chars=True)
        if text != _titler_data.active_layer.text:
            update_layers_list = True
        else:
            update_layers_list = False

        _titler_data.active_layer.text = text

        self._update_active_layout_font_properties()

        # We only want to update layer list data model when this called after user typing 
        if update_layers_list:
            self.layer_list.fill_data_model()

        self.view_editor.edit_area.queue_draw()

    def _update_active_layout_font_properties(self):
        family = self.font_families[self.font_select.get_active()]
        _titler_data.active_layer.font_family = family.get_name()

        _titler_data.active_layer.font_size = self.size_spin.get_value_as_int()
        
        face = FACE_REGULAR
        if self.bold_font.get_active() and self.italic_font.get_active():
            face = FACE_BOLD_ITALIC
        elif self.italic_font.get_active():
            face = FACE_ITALIC
        elif self.bold_font.get_active():
            face = FACE_BOLD
        _titler_data.active_layer.font_face = face
        
        align = ALIGN_LEFT
        if self.center_align.get_active():
            align = ALIGN_CENTER
        elif  self.right_align.get_active():
             align = ALIGN_RIGHT
        _titler_data.active_layer.alignment = align

        color = self.color_button.get_color()
        r, g, b = utils.hex_to_rgb(color.to_string())
        new_color = (r/65535.0, g/65535.0, b/65535.0, 1.0)        
        _titler_data.active_layer.color_rgba = new_color
        _titler_data.active_layer.fill_on = self.fill_on.get_active()
        
        # OUTLINE
        color = self.out_line_color_button.get_color()
        r, g, b = utils.hex_to_rgb(color.to_string())
        new_color2 = (r/65535.0, g/65535.0, b/65535.0, 1.0)    
        _titler_data.active_layer.outline_color_rgba = new_color2
        _titler_data.active_layer.outline_on = self.outline_on.get_active()
        _titler_data.active_layer.outline_width = self.out_line_size_spin.get_value()

        # SHADOW
        color = self.shadow_color_button.get_color()
        r, g, b = utils.hex_to_rgb(color.to_string())
        new_color3 = (r/65535.0, g/65535.0, b/65535.0)  
        _titler_data.active_layer.shadow_color_rgb = new_color3
        _titler_data.active_layer.shadow_on = self.shadow_on.get_active()
        _titler_data.active_layer.shadow_opacity = self.shadow_opa_spin.get_value()
        _titler_data.active_layer.shadow_xoff = self.shadow_xoff_spin.get_value()
        _titler_data.active_layer.shadow_yoff = self.shadow_yoff_spin.get_value()
        _titler_data.active_layer.shadow_blur = self.shadow_blur_spin.get_value()
        
        # GRADIENT
        if self.gradient_on.get_active() == True:
            color = self.gradient_color_button.get_color()
            r, g, b = utils.hex_to_rgb(color.to_string())
            new_color = (r/65535.0, g/65535.0, b/65535.0, 1.0)  
            _titler_data.active_layer.gradient_color_rgba = new_color
        else:
            _titler_data.active_layer.gradient_color_rgba = None
        _titler_data.active_layer.gradient_direction = self.direction_combo.get_active() # Combo indexes correspond with values of VERTICAL and HORIZONTAL
        
        
        self.view_editor.active_layer.update_rect = True
        _titler_data.active_layer.update_pango_layout()

    def _update_gui_with_active_layer_data(self):
        if _filling_layer_list:
            return
        
        # This a bit hackish, but works. Finding a method that blocks all
        # gui events from being added to event queue would be nice.
        self.block_updates = True
        
        # TEXT
        layer = _titler_data.active_layer
        self.text_view.get_buffer().set_text(layer.text)

        r, g, b, a = layer.color_rgba
        button_color = Gdk.RGBA(r, g, b, 1.0)
        self.color_button.set_rgba(button_color)

        if FACE_REGULAR == layer.font_face:
            self.bold_font.set_active(False)
            self.italic_font.set_active(False)
        elif FACE_BOLD == layer.font_face:
            self.bold_font.set_active(True)
            self.italic_font.set_active(False)
        elif FACE_ITALIC == layer.font_face:
            self.bold_font.set_active(False)
            self.italic_font.set_active(True) 
        else:#FACE_BOLD_ITALIC
            self.bold_font.set_active(True)
            self.italic_font.set_active(True)

        if layer.alignment == ALIGN_LEFT:
            self.left_align.set_active(True)
        elif layer.alignment == ALIGN_CENTER:
            self.center_align.set_active(True)
        else:#ALIGN_RIGHT
            self.right_align.set_active(True)

        self.size_spin.set_value(layer.font_size)
        
        try:
            combo_index = self.font_family_indexes_for_name[layer.font_family]
            self.font_select.set_active(combo_index)
        except:# if font family not found we'll use first. This happens e.g at start-up if "Times New Roman" not in system.
            family = self.font_families[0]
            layer.font_family = family.get_name()
            self.font_select.set_active(0)

        self.x_pos_spin.set_value(layer.x)
        self.y_pos_spin.set_value(layer.y)
        self.rotation_spin.set_value(layer.angle)
        
        self.fill_on.set_active(layer.fill_on)
                
        # OUTLINE
        r, g, b, a = layer.outline_color_rgba
        button_color = Gdk.RGBA(r, g, b, 1.0)
        self.out_line_color_button.set_rgba(button_color)
        self.out_line_size_spin.set_value(layer.outline_width)
        self.outline_on.set_active(layer.outline_on)
        
        # SHADOW
        r, g, b = layer.shadow_color_rgb
        button_color = Gdk.RGBA(r, g, b, 1.0)
        self.shadow_color_button.set_rgba(button_color)
        self.shadow_opa_spin.set_value(layer.shadow_opacity)
        self.shadow_xoff_spin.set_value(layer.shadow_xoff)
        self.shadow_yoff_spin.set_value(layer.shadow_yoff)
        self.shadow_on.set_active(layer.shadow_on)
        self.shadow_blur_spin.set_value(layer.shadow_blur)
        
        # GRADIENT
        if layer.gradient_color_rgba != None:
            r, g, b, a = layer.gradient_color_rgba
            button_color = Gdk.RGBA(r, g, b, 1.0)
            self.gradient_color_button.set_rgba(button_color)
            self.gradient_on.set_active(True)
        else:
            button_color = Gdk.RGBA(0.0, 0.0, 0.6, 1.0)
            self.gradient_color_button.set_rgba(button_color)
            self.gradient_on.set_active(False)
        self.direction_combo.set_active(layer.gradient_direction)
                
        self.block_updates = False



# --------------------------------------------------------- layer/s representation
class PangoTextLayout:
    """
    Object for drawing current active layer with Pango.
    
    Pixel size of layer can only be obtained when cairo context is available
    for drawing, so pixel size of layer is saved here.
    """
    def __init__(self, layer):
        self.load_layer_data(layer)
        
    def load_layer_data(self, layer): 
        self.text = layer.text
        self.font_desc = Pango.FontDescription(layer.get_font_desc_str())
        self.color_rgba = layer.color_rgba
        self.alignment = self._get_pango_alignment_for_layer(layer)
        self.pixel_size = layer.pixel_size # this is some placeholder default (100, 100), has no further meaning.
        self.fill_on = layer.fill_on
        self.gradient_color_rgba = layer.gradient_color_rgba

        self.outline_color_rgba = layer.outline_color_rgba
        self.outline_on = layer.outline_on
        self.outline_width = layer.outline_width

        self.shadow_on = layer.shadow_on
        self.shadow_color_rgb = layer.shadow_color_rgb
        self.shadow_opacity = layer.shadow_opacity
        self.shadow_xoff = layer.shadow_xoff
        self.shadow_yoff = layer.shadow_yoff
        self.shadow_blur = layer.shadow_blur
        
        self.gradient_color_rgba = layer.gradient_color_rgba
        self.gradient_direction = layer.gradient_direction

    # called from vieweditor draw vieweditor-> editorlayer->here
    def draw_layout(self, cr, x, y, rotation, xscale, yscale, view_editor):
        cr.save()

        fontmap = PangoCairo.font_map_new()
        context = fontmap.create_context()
        font_options = cairo.FontOptions()
        font_options.set_antialias(cairo.Antialias.GOOD)
        PangoCairo.context_set_font_options(context, font_options)
        context.changed()

        layout = Pango.Layout.new(context)
        
        layout.set_text(self.text, -1)
        layout.set_font_description(self.font_desc)
        layout.set_alignment(self.alignment)
        self.pixel_size = layout.get_pixel_size()

        # Shadow
        if self.shadow_on:
            cr.save()

            # Get colors.
            r, g, b = self.shadow_color_rgb
            a = self.shadow_opacity / 100.0

            # Blurred shadow need s own ImageSurface
            if self.shadow_blur != 0.0:
                blurred_img = cairo.ImageSurface(cairo.FORMAT_ARGB32, view_editor.profile_w,  view_editor.profile_h)
                cr_blurred = cairo.Context(blurred_img)
                cr_blurred.set_antialias(cairo.Antialias.GOOD)
                transform_cr = cr_blurred # Set draw transform_cr to cotext for newly created image.
            else:
                transform_cr = cr # Set draw transform_cr to out context.

            # Transform and set color.
            transform_cr.set_source_rgba(r, g, b, a)
            effective_shadow_xoff = self.shadow_xoff * xscale
            effective_shadow_yoff = self.shadow_yoff * yscale
            transform_cr.move_to(x + effective_shadow_xoff, y + effective_shadow_yoff)
            transform_cr.scale(xscale, yscale)
            transform_cr.rotate(rotation)

            # If no blur just draw layout on out context.
            if self.shadow_blur == 0.0:
                PangoCairo.update_layout(cr, layout)
                PangoCairo.show_layout(cr, layout)
                cr.restore()
            else:
                # If we have blur - draw shadow, blur it and then draw on out context.
                PangoCairo.update_layout(cr_blurred, layout)
                PangoCairo.show_layout(cr_blurred, layout)

                img2 = Image.frombuffer("RGBA", (blurred_img.get_width(), blurred_img.get_height()), blurred_img.get_data(), "raw", "RGBA", 0, 1)
                effective_blur = xscale * self.shadow_blur # This is not going to be exact
                                                           # on non-100% scales but let's try to get approximation. 
                img2 = img2.filter(ImageFilter.GaussianBlur(radius=int(effective_blur)))
                imgd = img2.tobytes()
                a = array.array('B',imgd)

                stride = blurred_img.get_width() * 4
                draw_surface = cairo.ImageSurface.create_for_data (a, cairo.FORMAT_ARGB32,
                                                              blurred_img.get_width(), blurred_img.get_height(), stride)
                cr.restore()
                cr.set_source_surface(draw_surface, 0, 0)
                cr.paint()

        # Text
        if self.fill_on:
            if self.gradient_color_rgba == None:
                cr.set_source_rgba(*self.color_rgba)
            else:
                w, h = self.pixel_size
                w = float(w) * xscale
                h = float(h) * yscale
                if self.gradient_direction == HORIZONTAL:
                    grad = cairo.LinearGradient (x, 0, x + w, 0)
                else:
                    grad = cairo.LinearGradient (0, y, 0, y + h)
                
                r, g, b, a = self.color_rgba
                rg, gg, bg, ag =  self.gradient_color_rgba 
                    
                CLIP_COLOR_GRAD_1 = (0,  r, g, b, 1)
                CLIP_COLOR_GRAD_2 = (1,  rg, gg, bg, 1)
                grad.add_color_stop_rgba(*CLIP_COLOR_GRAD_1)
                grad.add_color_stop_rgba(*CLIP_COLOR_GRAD_2)
                cr.set_source(grad)

            cr.move_to(x, y)
            cr.scale(xscale, yscale)
            cr.rotate(rotation)
            
            PangoCairo.update_layout(cr, layout)
            PangoCairo.show_layout(cr, layout)
        
        # Outline
        if self.outline_on:
            if self.fill_on == False: # case when user only wants outline we need to transform here
                cr.move_to(x, y)
                cr.scale(xscale, yscale)
                cr.rotate(rotation)
            PangoCairo.layout_path(cr, layout)
            cr.set_source_rgba(*self.outline_color_rgba)
            cr.set_line_width(self.outline_width)
            cr.stroke()
        
        cr.restore()

    def _get_pango_alignment_for_layer(self, layer):
        if layer.alignment == ALIGN_LEFT:
            return Pango.Alignment.LEFT
        elif layer.alignment == ALIGN_CENTER:
            return Pango.Alignment.CENTER
        else:
            return Pango.Alignment.RIGHT


class TextLayerListView(Gtk.VBox):

    def __init__(self, selection_changed_cb, layer_visible_toggled_cb):
        GObject.GObject.__init__(self)
        self.layer_icon = GdkPixbuf.Pixbuf.new_from_file(respaths.IMAGE_PATH + "text_layer.png")
        self.eye_icon = GdkPixbuf.Pixbuf.new_from_file(respaths.IMAGE_PATH + "eye.png")

        self.layer_visible_toggled_cb = layer_visible_toggled_cb

       # Datamodel: str
        self.storemodel = Gtk.ListStore(GdkPixbuf.Pixbuf, str, GdkPixbuf.Pixbuf)
 
        # Scroll container
        self.scroll = Gtk.ScrolledWindow()
        self.scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        # View
        self.treeview = Gtk.TreeView(model=self.storemodel)
        self.treeview.set_property("rules_hint", True)
        self.treeview.set_headers_visible(False)
        self.treeview.connect("button-press-event", self.button_press)
        self.treeview.set_activate_on_single_click(True)
        self.treeview.connect("row-activated", selection_changed_cb)
         
        tree_sel = self.treeview.get_selection()
        tree_sel.set_mode(Gtk.SelectionMode.SINGLE)
        #tree_sel.connect("changed", selection_changed_cb)

        # Cell renderers
        self.text_rend_1 = Gtk.CellRendererText()
        self.text_rend_1.set_property("ellipsize", Pango.EllipsizeMode.END)
        self.text_rend_1.set_property("font", "Sans Bold 10")
        self.text_rend_1.set_fixed_height_from_font(1)

        self.icon_rend_1 = Gtk.CellRendererPixbuf()
        self.icon_rend_1.props.xpad = 6
        self.icon_rend_1.set_fixed_size(40, 40)

        self.icon_rend_2 = Gtk.CellRendererPixbuf()
        self.icon_rend_2.props.xpad = 2
        self.icon_rend_2.set_fixed_size(20, 40)

        # Column view
        self.icon_col_1 = Gtk.TreeViewColumn("layer_icon")
        self.text_col_1 = Gtk.TreeViewColumn("layer_text")
        self.icon_col_2 = Gtk.TreeViewColumn("eye_icon")
        
        # Build column views
        self.icon_col_1.set_expand(False)
        self.icon_col_1.set_spacing(5)
        self.icon_col_1.pack_start(self.icon_rend_1, True)
        self.icon_col_1.add_attribute(self.icon_rend_1, 'pixbuf', 0)

        self.text_col_1.set_expand(True)
        self.text_col_1.set_spacing(5)
        self.text_col_1.set_sizing(Gtk.TreeViewColumnSizing.GROW_ONLY)
        self.text_col_1.set_min_width(150)
        self.text_col_1.pack_start(self.text_rend_1, True)
        self.text_col_1.add_attribute(self.text_rend_1, "text", 1)

        self.icon_col_2.set_expand(False)
        self.icon_col_2.set_spacing(5)
        self.icon_col_2.pack_start(self.icon_rend_2, True)
        self.icon_col_2.add_attribute(self.icon_rend_2, 'pixbuf', 2)

        # Add column views to view
        self.treeview.append_column(self.icon_col_1)
        self.treeview.append_column(self.text_col_1)
        self.treeview.append_column(self.icon_col_2)

        # Build widget graph and display
        self.scroll.add(self.treeview)
        self.pack_start(self.scroll, True, True, 0)
        self.scroll.show_all()

    def button_press(self, tree_view, event):
        if self.icon_col_1.get_width() + self.text_col_1.get_width() < event.x:
            path = self.treeview.get_path_at_pos(int(event.x), int(event.y))
            if path != None:
                self.layer_visible_toggled_cb(max(path[0]))

    def get_selected_row(self):
        model, rows = self.treeview.get_selection().get_selected_rows()
        try: # This has at times been called too often, but try may not be needed here anymore.
            return max(rows)[0]
        except:
            return -1

    def fill_data_model(self):
        """
        Creates displayed data.
        Displays icon, sequence name and sequence length
        """
        global _filling_layer_list
        _filling_layer_list = True
        self.storemodel.clear()
        for layer in _titler_data.layers:
            if layer.visible:
                visible_icon = self.eye_icon
            else:
                visible_icon = None 
            text = self.find_char_in_text(layer.text)
            row_data = [self.layer_icon, text, visible_icon]
            self.storemodel.append(row_data)
        
        self.scroll.queue_draw()
        _filling_layer_list = False

    def find_char_in_text(self, text):
        while text.find(" ") == 0 or text.find("\n") == 0:
            text = text[1:]
        line_end =text.find("\n")
        if  line_end != -1:
            text = text[:line_end]
        return text
        


class OpenFileThread(threading.Thread):
    
    def __init__(self, filename, view_editor):
        threading.Thread.__init__(self)
        self.filename = filename
        self.view_editor = view_editor

    def run(self):
        # This makes sure that the file has been written to disk
        while(self.view_editor.write_out_layers == True):
            time.sleep(0.1)
        
        open_in_bin_thread = projectaction.AddMediaFilesThread([self.filename])
        open_in_bin_thread.start()



class OpenTitlerItemThread(threading.Thread):
    
    def __init__(self, name, filepath, title_data, view_editor):
        threading.Thread.__init__(self)
        self.name = name
        self.filepath = filepath
        self.view_editor = view_editor
        self.title_data = title_data

    def run(self):
        # This makes sure that the file has been written to disk
        while(self.view_editor.write_out_layers == True):
            time.sleep(0.1)

        open_in_bin_thread = projectaction.AddTitleItemThread(self.name, self.filepath, self.title_data, self._completed_callback)
        open_in_bin_thread.start()

    def _completed_callback(self):
        GLib.idle_add(self._recreate_pango_layers)
    
    def _recreate_pango_layers(self):
        global _titler, _titler_data
        _titler_data.create_pango_layouts()
        _titler.load_titler_data()
        _titler.show_current_frame()