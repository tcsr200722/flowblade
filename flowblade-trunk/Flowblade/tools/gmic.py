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
    along with Flowblade Movie Editor. If not, see <http://www.gnu.org/licenses/>.
"""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('PangoCairo', '1.0')

from gi.repository import GLib, Gio
from gi.repository import Gtk, Gdk, GdkPixbuf
from gi.repository import Pango

import cairo
try:
    import mlt7 as mlt
except:
    import mlt
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser

import appconsts
import atomicfile
import cairoarea
import dialogutils
import editorstate
import editorpersistance
import gui
import guiutils
import glassbuttons
import gtkbuilder
import gtkevents
import mltinit
import mltprofiles
import positionbar
import respaths
import renderconsumer
import toolguicomponents
import toolsencoding
import userfolders
import utils
import utilsgtk

import gmicplayer
import gmicscript

MONITOR_WIDTH = 500
MONITOR_HEIGHT = 300 # initial value, this gets changed when material is loaded
CLIP_FRAMES_DIR = "/clip_frames"
RENDER_FRAMES_DIR = "/render_frames"
PREVIEW_FILE = "preview.png"
NO_PREVIEW_FILE = "fallback_thumb.png"

_gmic_found = False
_session_id = None

_app = None
_window = None

_player = None
_preview_render = None
_frame_writer = None
_effect_renderer = None

_current_path = None
_current_preview_surface = None
_current_dimensions = None
_current_fps = None
_current_profile_index = None
_render_data = None # toolsencoding.ToolsRenderData object
_last_load_file = None

_startup_data = None

_encoding_panel = None


_hamburger_popover = None
_hamburger_popover_menu = None
_script_popover = None
_script_popover_menu = None


#-------------------------------------------------- launch and inits
def test_availablity():
    global _gmic_found
    set_gmic_path()
    if editorstate.gmic_path != None:
        print("G'MIC found")
        _gmic_found = True
    else:
        print("G'MIC NOT found")

def set_gmic_path():
    if os.path.exists("/usr/bin/gmic") == True:
        editorstate.gmic_path = "/usr/bin/gmic"
    elif os.path.exists("/app/bin/gmic") == True: # File system and flatpak
        editorstate.gmic_path = "/app/bin/gmic"

def gmic_available():
    return _gmic_found
    
def launch_gmic(launch_data=None):
    if _gmic_found == False:
        primary_txt = _("G'Mic not found!")
        secondary_txt = _("G'Mic binary was not present at <b>/usr/bin/gmic</b>.\nInstall G'MIC to use this tool.")
        dialogutils.info_message(primary_txt, secondary_txt, gui.editor_window.window)
        return

    # Handle launching with clip data
    args = None
    if launch_data != None:
        clip, track = launch_data # from guicomponwnts._get_tool_integration_menu_item()
        args = ("path:" + str(clip.path), "clip_in:" + str(clip.clip_in), "clip_out:" + str(clip.clip_out))
        
    print("Launch gmic...")
    FLOG = open(userfolders.get_cache_dir() + "log_gmic", 'w')
    if args == None:
        subprocess.Popen([sys.executable, respaths.LAUNCH_DIR + "flowbladegmic"], stdin=FLOG, stdout=FLOG, stderr=FLOG)
    else:
        subprocess.Popen([sys.executable, respaths.LAUNCH_DIR + "flowbladegmic", args[0], args[1], args[2]], stdin=FLOG, stdout=FLOG, stderr=FLOG)

def _get_arg_value(args, key_str):
    for arg in sys.argv:
        parts = arg.split(":")
        if len(parts) > 1:
            if parts[0] == key_str:
                return parts[1]
    
    return None
        
def main(root_path, force_launch=False):
       
    gtk_version = "%s.%s.%s" % (Gtk.get_major_version(), Gtk.get_minor_version(), Gtk.get_micro_version())
    editorstate.gtk_version = gtk_version
    try:
        editorstate.mlt_version = mlt.LIBMLT_VERSION
    except:
        editorstate.mlt_version = "0.0.99" # magic string for "not found"

    global _session_id
    _session_id = int(time.time() * 1000) # good enough

    # Set paths.
    respaths.set_paths(root_path)
    set_gmic_path() # Flatpak has gmic binary in different place.

    # Write stdout to log file
    userfolders.init()
    sys.stdout = open(userfolders.get_cache_dir() + "log_gmic", 'w')

    # Init gmic tool session dirs
    if os.path.exists(get_session_folder()):
        shutil.rmtree(get_session_folder())
        
    os.mkdir(get_session_folder())

    init_frames_dirs()

    # Load editor prefs and apply themes images paths.
    editorpersistance.load()

    # Create app.
    app = GMicApplication()
    global _app
    _app = app
    app.run(None)

    
class GMicApplication(Gtk.Application):
    def __init__(self, *args, **kwargs):
        Gtk.Application.__init__(self, application_id=None,
                                 flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.connect("activate", self.on_activate)

    def on_activate(self, data=None):
        # Set monitor sizes
        scr_w, scr_h = utilsgtk.get_combined_monitors_size()
        editorstate.SCREEN_WIDTH = scr_w
        editorstate.SCREEN_HEIGHT = scr_h
        if editorstate.screen_size_large_height() == True and editorstate.screen_size_small_width() == False:
            global MONITOR_WIDTH, MONITOR_HEIGHT
            MONITOR_WIDTH = 650
            MONITOR_HEIGHT = 400 # initial value, this gets changed when material is loaded

        # Themes
        gui.apply_theme()
        
        # Init mlt.
        repo = mltinit.init_with_translations()

        # Load preset gmic scripts
        gmicscript.load_preset_scripts_xml()
        
        global _window
        _window = GmicWindow()
        _window.pos_bar.set_dark_bg_color()

        os.putenv('SDL_WINDOWID', str(_window.monitor.get_window().get_xid()))

        # Start with a clip loaded if data provided
        if len(sys.argv) > 1:
            path = _get_arg_value(sys.argv, "path")
            mark_in = int(_get_arg_value(sys.argv, "clip_in"))
            mark_out = int(_get_arg_value(sys.argv, "clip_out"))
            global _startup_data
            _startup_data = (path, mark_in, mark_out)
            GLib.idle_add(_load_startup_data)
        
        self.add_window(_window)


def _load_startup_data():
    path, mark_in, mark_out = _startup_data
    _do_file_load(path)
    GLib.idle_add(_finish_load_startup_data)

def _finish_load_startup_data():
    path, mark_in, mark_out = _startup_data
    _player.producer.mark_in = mark_in
    _player.producer.mark_out = mark_out

    _window.update_marks_display()
    _window.pos_bar.update_display_from_producer(_player.producer)
    _window.update_render_status_info()
    
def init_frames_dirs():
    os.mkdir(get_clip_frames_dir())
    os.mkdir(get_render_frames_dir())

#----------------------------------------------- session folders and files
def get_session_folder():
    return userfolders.get_cache_dir() + appconsts.GMIC_DIR + "/session_" + str(_session_id)

def get_clip_frames_dir():
    return get_session_folder() + CLIP_FRAMES_DIR

def get_render_frames_dir():
    return get_session_folder() + RENDER_FRAMES_DIR
    
def get_current_frame_file():
    return get_clip_frames_dir() + "/frame" + str(_player.current_frame()) + ".png"

def get_preview_file():
    return get_session_folder() + "/" + PREVIEW_FILE
    
# --------------------------------------------- load clip
def open_clip_dialog():
    
    file_select = Gtk.FileChooserDialog(_("Select Video Media"), _window, Gtk.FileChooserAction.OPEN,
                                    (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                                    Gtk.STOCK_OPEN, Gtk.ResponseType.OK))

    file_select.set_default_response(Gtk.ResponseType.CANCEL)
    file_select.set_select_multiple(False)

    media_filter = utilsgtk.get_video_source_file_filter()
    file_select.add_filter(media_filter)

    if _last_load_file != None:
        file_select.set_current_folder(os.path.dirname(_last_load_file))
    elif ((editorpersistance.prefs.open_in_last_opended_media_dir == True) 
        and (editorpersistance.prefs.last_opened_media_dir != None)):
        file_select.set_current_folder(editorpersistance.prefs.last_opened_media_dir)
    
    file_select.connect('response', _open_files_dialog_cb)

    file_select.set_modal(True)
    file_select.show()

def _open_files_dialog_cb(file_select, response_id):
    filenames = file_select.get_filenames()
    file_select.destroy()

    if response_id != Gtk.ResponseType.OK:
        return
    if len(filenames) == 0:
        return

    # Only accept video files
    if utils.get_file_type(filenames[0]) != "video":
        return

    _do_file_load(filenames[0])

def _do_file_load(file_path, use_default_profile=False):
    global _last_load_file
    _last_load_file = file_path
    
    global _current_path, _render_data

    # if another clip has already been opened then we need to shutdown players.
    # and reset render data
    if _current_path != None:
        _render_data = None
        if _player != None:
            _player.shutdown()
        if _effect_renderer != None:
            _effect_renderer.shutdown()

    _current_path = file_path

    # Finish clip open when dialog has been destroyed
    GLib.idle_add(_finish_clip_open, use_default_profile)
    
def _finish_clip_open(use_default_profile):
    if use_default_profile == False:
        new_profile_index = gmicplayer.set_current_profile(_current_path)
        new_profile = mltprofiles.get_profile_for_index(new_profile_index)
    else:
        new_profile_index = mltprofiles.get_default_profile_index()
        new_profile = mltprofiles.get_default_profile()
        gmicplayer.set_current_profile_as_default_profile()

    global _current_dimensions, _current_fps, _current_profile_index
    _current_dimensions = (new_profile.width(), new_profile.height(), 1.0)
    _current_fps = float(new_profile.frame_rate_num())/float(new_profile.frame_rate_den())
    _current_profile_index = new_profile_index

    global _player, _frame_writer
    _player = gmicplayer.GmicPlayer(_current_path)
    _player.set_display_widget(_window.monitor)
    _window.monitor.connect("size-allocate", lambda w, e:_player.display_resized())
 
    _frame_writer = gmicplayer.PreviewFrameWriter(_current_path)

    # Set SDL consumer version to be used.
    #if editorstate.mlt_version_is_greater_correct("7.28.0") or editorstate.force_sdl2 == True \
    #    or editorstate.app_running_from == editorstate.RUNNING_FROM_FLATPAK:
    if editorstate.force_sdl2 == True:
        gmicplayer.set_sdl_consumer_version(gmicplayer.SDL_2)
    else:
        gmicplayer.set_sdl_consumer_version(gmicplayer.SDL_1)
            
    _window.set_fps()
    _window.set_monitor_sizes()
    if use_default_profile == False:
        _window.init_for_new_clip(_current_path, new_profile.description())
        _window.set_widgets_sensitive(True)
    else:
        _window.set_widgets_sensitive(False)
    _window.render_button.set_sensitive(False)
    _window.encode_desc.set_markup("<small>" + _("not set")  + "</small>")
    _player.create_sdl_consumer()
    _player.connect_and_start()

#-------------------------------------------------- script setting and save/load
def script_menu_item_selected(widget, action, script):
    if _window.action_select.get_active() == False:
        _window.script_view.get_buffer().set_text(script.script)
    else:
        buf = _window.script_view.get_buffer()
        buf.insert(buf.get_end_iter(), " " + script.script)
    _window.preset_label.set_text(script.name)

def save_script_dialog(callback):
    dialog = Gtk.FileChooserDialog(_("Save Gmic Script As"), None, 
                                   Gtk.FileChooserAction.SAVE, 
                                   (_("Cancel"), Gtk.ResponseType.CANCEL,
                                   _("Save"), Gtk.ResponseType.ACCEPT))
    dialog.set_action(Gtk.FileChooserAction.SAVE)
    dialog.set_current_name("gmic_script")
    dialog.set_do_overwrite_confirmation(True)
    dialog.set_select_multiple(False)
    dialog.connect('response', callback)
    dialog.show()

def _save_script_dialog_callback(dialog, response_id):
    if response_id == Gtk.ResponseType.ACCEPT:
        file_path = dialog.get_filenames()[0]
        buf = _window.script_view.get_buffer()
        script_text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), include_hidden_chars=True)
        with atomicfile.AtomicFileWriter(file_path, "w") as afw:
            script_file = afw.get_file()
            script_file.write(script_text)
        dialog.destroy()
    else:
        dialog.destroy()

def load_script_dialog(callback):
    dialog = Gtk.FileChooserDialog(_("Load Gmic Script"), None, 
                                   Gtk.FileChooserAction.OPEN, 
                                   (_("Cancel"), Gtk.ResponseType.CANCEL,
                                    _("OK"), Gtk.ResponseType.ACCEPT))
    dialog.set_action(Gtk.FileChooserAction.OPEN)
    dialog.set_select_multiple(False)
    dialog.connect('response', callback)
    dialog.show()

def _load_script_dialog_callback(dialog, response_id):
    if response_id == Gtk.ResponseType.ACCEPT:
        filename = dialog.get_filenames()[0]
        args_file = open(filename)
        args_text = args_file.read()
        _window.script_view.get_buffer().set_text(args_text)
        dialog.destroy()
    else:
        dialog.destroy()

#-------------------------------------------------- menu
def _hamburger_menu_callback(widget, action, msg):
    if msg == "load":
        open_clip_dialog()
    elif msg == "close":
        _shutdown()
    elif msg == "docs":
        webbrowser.open(url="http://gmic.eu/", new=0, autoraise=True)

#-------------------------------------------------- player buttons
def prev_pressed(delta=-1):
    _player.seek_delta(delta)
    update_frame_displayers()
        
def next_pressed(delta=1):
    _player.seek_delta(delta)
    update_frame_displayers()

def start_pressed():
    _player.seek_frame(0)
    update_frame_displayers()
        
def end_pressed():
    _player.seek_delta(_player.get_active_length() - 1)
    update_frame_displayers()
    
def mark_in_pressed():
    _player.producer.mark_in = _player.current_frame()
    if _player.producer.mark_in > _player.producer.mark_out:
        _player.producer.mark_out = -1

    _window.update_marks_display()
    _window.pos_bar.update_display_from_producer(_player.producer)
    _window.update_render_status_info()

def mark_out_pressed():
    _player.producer.mark_out = _player.current_frame()
    if _player.producer.mark_out < _player.producer.mark_in:
        _player.producer.mark_in = -1

    _window.update_marks_display()
    _window.pos_bar.update_display_from_producer(_player.producer)
    _window.update_render_status_info()
    
def marks_clear_pressed():
    _player.producer.mark_in = -1
    _player.producer.mark_out = -1

    _window.update_marks_display()
    _window.pos_bar.update_display_from_producer(_player.producer)
    _window.update_render_status_info()

def to_mark_in_pressed():
    if _player.producer.mark_in != -1:
        _player.seek_frame(_player.producer.mark_in)
    update_frame_displayers()
    
def to_mark_out_pressed():
    if _player.producer.mark_out != -1:
        _player.seek_frame(_player.producer.mark_out)
    update_frame_displayers()

def update_frame_displayers():
    frame = _player.current_frame()
    _window.tc_display.set_frame(frame)
    _window.pos_bar.update_display_from_producer(_player.producer)

#-------------------------------------------------- render and preview
def render_output():
    buf = _window.script_view.get_buffer()
    user_script = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)

    out_folder = _window.out_folder.get_filenames()[0] + "/"
    if out_folder == (os.path.expanduser("~") + "/"):
        return

    _window.render_status_info.set_markup("")
    _window.set_widgets_sensitive(False)
    _window.render_percentage.set_sensitive(True)
    _window.render_status_info.set_sensitive(True)
    _window.render_progress_bar.set_sensitive(True)
    _window.stop_button.set_sensitive(True)
    _window.render_button.set_sensitive(False)
    _window.close_button.set_sensitive(False)
    _window.encode_settings_button.set_sensitive(False)
    _window.encode_desc.set_sensitive(False)
    _window.hamburger_launcher.widget.set_sensitive(False)
    _window.load_button.set_sensitive(False)
        
    global _effect_renderer
    _effect_renderer = GmicEffectRendererer(user_script, out_folder)
    _effect_renderer.start()

def abort_render():
    _effect_renderer.abort_render()

def render_preview_frame():
    _frame_writer.write_frame(get_clip_frames_dir() + "/", _player.current_frame())
    render_current_frame_preview()
    _window.preview_monitor.queue_draw()
    
def render_current_frame_preview():
    _window.preview_info.set_markup("<small>" + _("Rendering preview...") + "</small>" )
    
    buf = _window.script_view.get_buffer()
    view_text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
    
    global _preview_render
    _preview_render = GmicPreviewRendererer(view_text)
    _preview_render.start()

def _encode_settings_clicked():
    toolsencoding.create_widgets(_current_profile_index)
        
    global _encoding_panel
    _encoding_panel = toolsencoding.get_encoding_panel(_render_data)

    if _render_data == None and toolsencoding.widgets.file_panel.movie_name.get_text() == "movie":
        toolsencoding.widgets.file_panel.movie_name.set_text(os.path.basename(_current_path).split(".")[0] + "_gmic")

    align = dialogutils.get_default_alignment(_encoding_panel)
    
    dialog = Gtk.Dialog(_("Video Encoding Settings"),
                        None,
                        None,
                        (_("Cancel"), Gtk.ResponseType.REJECT,
                         _("Set Encoding"), Gtk.ResponseType.ACCEPT))
    dialog.vbox.pack_start(align, True, True, 0)
    dialogutils.set_outer_margins(dialog.vbox)
    dialog.set_resizable(False)

    dialog.connect('response', _encode_settings_callback)
    dialog.show_all()

def _encode_settings_callback(dialog, response_id):
    if response_id == Gtk.ResponseType.ACCEPT:
        global _render_data
        _render_data = toolsencoding.get_render_data_for_current_selections()
        _window.update_encode_desc()
    
    dialog.destroy()
        
        
#-------------------------------------------------- shutdown
def _shutdown():
    # Stop all possibly running threads and consumers
    if _player != None:
        _player.shutdown()
    if _effect_renderer != None:
        _effect_renderer.shutdown()

    # Delete session folder
    shutil.rmtree(get_session_folder())

    # Close app.
    _app.quit()


#------------------------------------------------- window
class GmicWindow(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self, Gtk.WindowType.TOPLEVEL)
        
        app_icon = GdkPixbuf.Pixbuf.new_from_file(respaths.IMAGE_PATH + "flowbladetoolicon.png")
        self.set_icon(app_icon)
        hamburger_launcher_surface = guiutils.get_cairo_image("hamburger")
        psize = 22
        self.hamburger_launcher = toolguicomponents.PressLaunchSurface(self.hamburger_launch_pressed, hamburger_launcher_surface, psize, psize)
        
        # Load media row
        self.load_button = Gtk.Button(label=_("Load Clip"))
        self.load_button.connect("clicked", lambda w: open_clip_dialog())

        self.media_info = Gtk.Label()
        self.media_info.set_markup("<small>" + _("no clip loaded") + "</small>")

        load_row = Gtk.HBox(False, 2)
        load_row.pack_start(self.hamburger_launcher.widget, False, False, 0)
        load_row.pack_start(guiutils.get_pad_label(6, 2), False, False, 0)
        load_row.pack_start(self.load_button, False, False, 0)
        load_row.pack_start(guiutils.get_pad_label(6, 2), False, False, 0)
        load_row.pack_start(self.media_info, False, False, 0)
        load_row.pack_start(Gtk.Label(), True, True, 0)
        load_row.set_margin_bottom(8)

        # Clip monitor
        self.monitor = Gtk.Label()
        self.monitor.set_size_request(MONITOR_WIDTH, MONITOR_HEIGHT)
        self.monitors_holder = Gtk.Stack()    
        self.monitors_holder.add_named(self.monitor, "monitor") # we need to put Gtk.Label inside something with a XWindow to work with SDL.
                
        left_vbox = Gtk.VBox(False, 0)
        left_vbox.pack_start(load_row, False, False, 0)
        left_vbox.pack_start(self.monitors_holder, True, True, 0)

        self.preview_info = Gtk.Label()
        self.preview_info.set_markup("<small>" + _("no preview") + "</small>" )
        preview_info_row = Gtk.HBox()
        preview_info_row.pack_start(self.preview_info, False, False, 0)
        preview_info_row.pack_start(Gtk.Label(), True, True, 0)
        preview_info_row.set_margin_top(6)
        preview_info_row.set_margin_bottom(8)

        self.preview_monitor = cairoarea.CairoDrawableArea2(MONITOR_WIDTH, MONITOR_HEIGHT, self._draw_preview)

        self.no_preview_icon = cairo.ImageSurface.create_from_png(respaths.IMAGE_PATH + NO_PREVIEW_FILE)

        right_vbox = Gtk.VBox(False, 2)
        right_vbox.pack_start(preview_info_row, False, False, 0)
        right_vbox.pack_start(self.preview_monitor, True, True, 0)

        # Monitors panel
        monitors_panel = Gtk.HBox(False, 2)
        monitors_panel.pack_start(left_vbox, False, False, 0)
        monitors_panel.pack_start(Gtk.Label(), True, True, 0)
        monitors_panel.pack_start(right_vbox, False, False, 0)

        # Control row
        self.tc_display = toolguicomponents.MonitorTCDisplay()
        self.tc_display.use_internal_frame = True
        self.tc_display.widget.set_valign(Gtk.Align.CENTER)
        self.tc_display.use_internal_fps = True
        
        self.pos_bar = positionbar.PositionBar(False)
        self.pos_bar.set_listener(self.position_listener)
        pos_bar_frame = Gtk.HBox()
        pos_bar_frame.add(self.pos_bar.widget)
        pos_bar_frame.set_margin_top(10)
        pos_bar_frame.set_margin_bottom(9)
        pos_bar_frame.set_margin_start(6)
        pos_bar_frame.set_margin_end(2)
            
        self.control_buttons = glassbuttons.GmicButtons()
        pressed_callback_funcs = [prev_pressed,
                                  next_pressed,
                                  mark_in_pressed,
                                  mark_out_pressed,
                                  marks_clear_pressed,
                                  to_mark_in_pressed,
                                  to_mark_out_pressed]
        self.control_buttons.set_callbacks(pressed_callback_funcs)
        if editorpersistance.prefs.buttons_style == 2: # NO_DECORATIONS
            self.control_buttons.no_decorations = True 
        
        self.preview_button = Gtk.Button(label=_("Preview"))
        self.preview_button.connect("clicked", lambda w: render_preview_frame())
                            
        control_panel = Gtk.HBox(False, 2)
        control_panel.pack_start(self.tc_display.widget, False, False, 0)
        control_panel.pack_start(pos_bar_frame, True, True, 0)
        control_panel.pack_start(self.control_buttons.widget, False, False, 0)
        control_panel.pack_start(guiutils.pad_label(2, 2), False, False, 0)
        control_panel.pack_start(self.preview_button, False, False, 0)
        control_panel.set_margin_top(4)

        preview_panel = Gtk.VBox(False, 2)
        preview_panel.pack_start(monitors_panel, False, False, 0)
        preview_panel.pack_start(control_panel, False, False, 0)
        preview_panel.set_margin_bottom(8)

        # Script area 
        # Script selector menu launcher
        self.preset_label = Gtk.Label()
        self.present_event_box = gtkbuilder.EventBox(self.preset_label, "button-press-event", self.script_menu_lauched)

        self.script_menu = toolguicomponents.PressLaunch(self.script_menu_lauched)
        
        self.action_select = Gtk.CheckButton()
        self.action_select.set_active(False)
        self.action_select.set_margin_end(4)
                
        self.action_label = Gtk.Label(label=_("Add to Script"))

        preset_row = Gtk.HBox(False, 2)
        preset_row.pack_start(self.present_event_box, False, False, 0)
        preset_row.pack_start(self.script_menu.widget, False, False, 0)
        preset_row.pack_start(guiutils.pad_label(2, 30), False, False, 0)
        preset_row.pack_start(Gtk.Label(), True, True, 0)
        preset_row.pack_start(self.action_select, False, False, 0)
        preset_row.pack_start(self.action_label, False, False, 0)
                
        self.script_view = Gtk.TextView()
        self.script_view.set_sensitive(False)
        self.script_view.set_pixels_above_lines(2)
        self.script_view.set_left_margin(2)
        self.script_view.set_wrap_mode(Gtk.WrapMode.CHAR)
        
        script_sw = Gtk.ScrolledWindow()
        script_sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        script_sw.add(self.script_view)
        script_sw.set_size_request(MONITOR_WIDTH - 100, 125)

        self.out_view = Gtk.TextView()
        self.out_view.set_sensitive(False)
        self.out_view.set_pixels_above_lines(2)
        self.out_view.set_left_margin(2)
        self.out_view.set_wrap_mode(Gtk.WrapMode.WORD)
        fd = Pango.FontDescription.from_string("Sans 8")
        self.out_view.override_font(fd)

        out_sw = Gtk.ScrolledWindow()
        out_sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        out_sw.add(self.out_view)
        out_sw.set_size_request(MONITOR_WIDTH - 150, 100)
        
        script_vbox = Gtk.VBox(False, 2)
        script_vbox.pack_start(preset_row, False, False, 0)
        script_vbox.pack_start(script_sw, True, True, 0)
        script_vbox.pack_start(out_sw, True, True, 0)

        # Render panel
        self.mark_in_label = guiutils.bold_label(_("Mark In:"))
        self.mark_out_label = guiutils.bold_label(_("Mark Out:"))
        self.length_label = guiutils.bold_label(_("Length:"))
        
        self.mark_in_info = Gtk.Label(label="-")
        self.mark_out_info = Gtk.Label(label="-")
        self.length_info = Gtk.Label(label="-")

        in_row = guiutils.get_two_column_box(self.mark_in_label, self.mark_in_info, 150)
        out_row = guiutils.get_two_column_box(self.mark_out_label, self.mark_out_info, 150)
        length_row = guiutils.get_two_column_box(self.length_label, self.length_info, 150)
        
        marks_row = Gtk.VBox(False, 2)
        marks_row.pack_start(in_row, True, True, 0)
        marks_row.pack_start(out_row, True, True, 0)
        marks_row.pack_start(length_row, True, True, 0)

        self.out_folder = gtkbuilder.get_file_chooser_button(_("Select Folder"))
        self.out_folder.set_action(Gtk.FileChooserAction.SELECT_FOLDER)
        self.out_folder.connect_selection_changed(None, self.folder_selection_changed)
        self.out_label = Gtk.Label(label=_("Frames Folder:"))
        
        self.frame_name = Gtk.Entry()
        self.frame_name.set_text("frame")
        self.extension_label = Gtk.Label()
        self.extension_label.set_markup("<small>XXXX.png</small>")

        out_folder_row = guiutils.get_left_justified_box([self.out_label, guiutils.pad_label(12, 2), \
                            self.out_folder, guiutils.pad_label(24, 2), self.frame_name, \
                            guiutils.pad_label(2, 2), self.extension_label])

        self.encode_check_label = Gtk.Label(label=_("Encode Video"))
        self.encode_check = Gtk.CheckButton()
        self.encode_check.set_active(False)
        self.encode_check.set_margin_end(4)
        self.encode_check.connect("toggled", lambda w:self.update_encode_sensitive())
        
        self.encode_settings_button = Gtk.Button(label=_("Encoding settings"))
        self.encode_settings_button.connect("clicked", lambda w:_encode_settings_clicked())
        self.encode_desc = Gtk.Label()
        self.encode_desc.set_markup("<small>" + _("not set")  + "</small>")
        self.encode_desc.set_ellipsize(Pango.EllipsizeMode.END)
        self.encode_desc.set_max_width_chars(32)

        encode_row = Gtk.HBox(False, 2)
        encode_row.pack_start(self.encode_check, False, False, 0)
        encode_row.pack_start(self.encode_check_label, False, False, 0)
        encode_row.pack_start(guiutils.pad_label(48, 12), False, False, 0)
        encode_row.pack_start(self.encode_settings_button, False, False, 0)
        encode_row.pack_start(guiutils.pad_label(6, 12), False, False, 0)
        encode_row.pack_start(self.encode_desc, False, False, 0)
        encode_row.pack_start(Gtk.Label(), True, True, 0)
        encode_row.set_margin_bottom(6)

        self.render_percentage = Gtk.Label(label="")
        
        self.status_no_render = _("Set Mark In, Mark Out and Frames Folder for valid render")
         
        self.render_status_info = Gtk.Label()
        self.render_status_info.set_markup("<small>" + self.status_no_render  + "</small>") 

        render_status_row = Gtk.HBox(False, 2)
        render_status_row.pack_start(self.render_percentage, False, False, 0)
        render_status_row.pack_start(Gtk.Label(), True, True, 0)
        render_status_row.pack_start(self.render_status_info, False, False, 0)

        render_status_row.set_margin_bottom(6)

        self.render_progress_bar = Gtk.ProgressBar()
        self.render_progress_bar.set_valign(Gtk.Align.CENTER)

        self.stop_button = guiutils.get_sized_button(_("Stop"), 100, 32)
        self.stop_button.connect("clicked", lambda w:abort_render())
        self.render_button = guiutils.get_sized_button(_("Render"), 100, 32)
        self.render_button.connect("clicked", lambda w:render_output())

        render_row = Gtk.HBox(False, 2)
        render_row.pack_start(self.render_progress_bar, True, True, 0)
        render_row.pack_start(guiutils.pad_label(12, 2), False, False, 0)
        render_row.pack_start(self.stop_button, False, False, 0)
        render_row.pack_start(self.render_button, False, False, 0)

        render_vbox = Gtk.VBox(False, 2)
        render_vbox.pack_start(marks_row, False, False, 0)
        render_vbox.pack_start(Gtk.Label(), True, True, 0)
        render_vbox.pack_start(encode_row, False, False, 0)
        render_vbox.pack_start(Gtk.Label(), True, True, 0)
        render_vbox.pack_start(out_folder_row, False, False, 0)
        render_vbox.pack_start(Gtk.Label(), True, True, 0)
        render_vbox.pack_start(render_status_row, False, False, 0)
        render_vbox.pack_start(render_row, False, False, 0)
        render_vbox.pack_start(guiutils.pad_label(24, 24), False, False, 0)
        
        # Script work panel
        script_work_panel = Gtk.HBox(False, 2)
        script_work_panel.pack_start(script_vbox, False, False, 0)
        script_work_panel.pack_start(guiutils.pad_label(12, 2), False, False, 0)
        script_work_panel.pack_start(render_vbox, True, True, 0)

        self.load_script = Gtk.Button(label=_("Load Script"))
        self.load_script.connect("clicked", lambda w:load_script_dialog(_load_script_dialog_callback))
        self.save_script = Gtk.Button(label=_("Save Script"))
        self.save_script.connect("clicked", lambda w:save_script_dialog(_save_script_dialog_callback))

        exit_b = guiutils.get_sized_button(_("Close"), 150, 32)
        exit_b.connect("clicked", lambda w:_shutdown())
        self.close_button = exit_b
        
        editor_buttons_row = Gtk.HBox()
        editor_buttons_row.pack_start(self.load_script, False, False, 0)
        editor_buttons_row.pack_start(self.save_script, False, False, 0)
        editor_buttons_row.pack_start(Gtk.Label(), True, True, 0)
        editor_buttons_row.pack_start(exit_b, False, False, 0)

        # Build window
        pane = Gtk.VBox(False, 2)
        pane.pack_start(preview_panel, False, False, 0)
        pane.pack_start(script_work_panel, False, False, 0)
        pane.pack_start(editor_buttons_row, False, False, 0)

        align = guiutils.set_margins(pane, 12, 12, 12, 12)

        script = gmicscript.get_default_script()
        self.script_view.get_buffer().set_text(script.script)
        self.preset_label.set_text(script.name)

        self.update_encode_sensitive()

        # Connect global key listener
        self.global_key_controller = gtkevents.KeyPressEventAdapter(self, _global_key_down_listener, user_data=None, capture=True)
        
        # Set pane and show window
        self.add(align)
        self.set_title(_("G'MIC Effects"))
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_widgets_sensitive(False)
        self.show_all()
        self.set_resizable(False)
        self.set_active_state(False)

        GLib.idle_add(_do_file_load, respaths.BLACK_IMAGE_PATH, True)
            
    def init_for_new_clip(self, clip_path, profile_name):
        self.clip_path = clip_path
        self.set_active_state(True)
        self.pos_bar.update_display_from_producer(_player.producer)
        self.media_info.set_markup("<small>" + os.path.basename(clip_path) + ", " + profile_name + "</small>")

    def update_marks_display(self):
        if _player.producer.mark_in == -1:
            self.mark_in_info.set_text("-")
        else:
            self.mark_in_info.set_text(utils.get_tc_string_with_fps(_player.producer.mark_in, _current_fps))
        
        if  _player.producer.mark_out == -1:
            self.mark_out_info.set_text("-")
        else:
            self.mark_out_info.set_text(utils.get_tc_string_with_fps(_player.producer.mark_out + 1, _current_fps))

        if _player.producer.mark_in == -1 or  _player.producer.mark_out == -1:
            self.length_info.set_text("-")
        else:
            self.length_info.set_text(str(_player.producer.mark_out - _player.producer.mark_in + 1) + " " + _("frames"))

        self.mark_in_info.queue_draw()
        self.mark_out_info.queue_draw()
        self.length_info.queue_draw()

    def update_render_status_info(self):
        if _player == None:# this gets called too on startup to set text before player is ready
            self.render_status_info.set_markup("<small>" + self.status_no_render  + "</small>")
            self.render_button.set_sensitive(False)
            return
        
        if  _player.producer.mark_in == -1 or _player.producer.mark_out == -1 \
            or self.out_folder.get_filename() == None:
            self.render_status_info.set_markup("<small>" + self.status_no_render  + "</small>")
            self.render_button.set_sensitive(False)
        else:
            length = _player.producer.mark_out - _player.producer.mark_in + 1
            video_info = _(" no video file")
            if self.encode_check.get_active() == True:
                video_info = _(" render video file")
            info_str = str(length) + _(" frame(s),") + video_info
            self.render_status_info.set_markup("<small>" + info_str +  "</small>")
            self.render_button.set_sensitive(True)
            
    def folder_selection_changed(self, chooser, data):
        self.update_render_status_info()

    def hamburger_launch_pressed(self, widget, event):
        
        global _hamburger_popover, _hamburger_popover_menu
    
        _hamburger_popover_menu = toolguicomponents.menu_clear_or_create(_hamburger_popover_menu)

        main_section = Gio.Menu.new()    
        toolguicomponents.add_menu_action(_app, main_section, _("Load Clip"),  "mainmenu.load", "load", _hamburger_menu_callback)
        toolguicomponents.add_menu_action(_app, main_section, _("G'Mic Webpage"),  "mainmenu.docs", "docs", _hamburger_menu_callback)
        _hamburger_popover_menu.append_section(None, main_section)

        close_section = Gio.Menu.new()    
        toolguicomponents.add_menu_action(_app, close_section, _("Close"),  "mainmenu.close", "close", _hamburger_menu_callback)
        _hamburger_popover_menu.append_section(None, close_section)
        
        _hamburger_popover = Gtk.Popover.new_from_model(widget, _hamburger_popover_menu)
        self.hamburger_launcher.connect_launched_menu(_hamburger_popover)
        _hamburger_popover.show()

    def script_menu_lauched(self, widget, event):
        
        global _script_popover, _script_popover_menu
    
        _script_popover_menu = toolguicomponents.menu_clear_or_create(_script_popover_menu)

        script_groups = gmicscript.get_script_groups()

        for script_group in script_groups:
            group_name, group = script_group
            
            sub_menu = Gio.Menu.new()
            _script_popover_menu.append_submenu(group_name, sub_menu)

            for script in group:
                label = script.name
                item_id = script.name.lower().replace(" ", "_")
                sub_menu.append(label, "app." + item_id) 
                
                action = Gio.SimpleAction(name=item_id)
                action.connect("activate", script_menu_item_selected, script)
                _app.add_action(action)

        _script_popover = Gtk.Popover.new_from_model(widget, _script_popover_menu)
        _script_popover.show()
    
    def set_active_state(self, active):
        self.monitor.set_sensitive(active)
        self.pos_bar.widget.set_sensitive(active)

    def set_fps(self):
        self.tc_display.fps = _current_fps
        
    def position_listener(self, normalized_pos, length):
        frame = int(normalized_pos * length)
        self.tc_display.set_frame(frame)
        _player.seek_frame(frame)
        self.pos_bar.widget.queue_draw()

    def _draw_preview(self, event, cr, allocation):
        x, y, w, h = allocation

        if _current_preview_surface != None:
            width, height, pixel_aspect = _current_dimensions
            scale = float(MONITOR_WIDTH) / float(width)
            cr.scale(scale * pixel_aspect, scale)
            cr.set_source_surface(_current_preview_surface, 0, 0)
            cr.paint()
        else:
            cr.set_source_rgb(0.0, 0.0, 0.0)
            cr.rectangle(0, 0, w, h)
            cr.fill()
    
    def set_monitor_sizes(self):
        w, h, pixel_aspect = _current_dimensions
        new_height = MONITOR_WIDTH * (float(h)/float(w)) * pixel_aspect
        self.monitor.set_size_request(MONITOR_WIDTH, new_height)
        self.preview_monitor.set_size_request(MONITOR_WIDTH, new_height)

    def update_encode_sensitive(self):
        value = self.encode_check.get_active()
        self.encode_settings_button.set_sensitive(value)
        self.encode_desc.set_sensitive(value)
        self.update_render_status_info()

    def update_encode_desc(self):
        if _render_data == None:
            desc_str = "not set" 
        else:
            args_vals = toolsencoding.get_args_vals_list_for_render_data(_render_data)
            desc_str = toolsencoding.get_encoding_desc(args_vals) + ", " + _render_data.file_name + _render_data.file_extension

        self.encode_desc.set_markup("<small>" + desc_str + "</small>")
        self.encode_desc.set_ellipsize(Pango.EllipsizeMode.END)

    def set_widgets_sensitive(self, value):
        self.monitor.set_sensitive(value)
        self.preview_info.set_sensitive(value)
        self.preview_monitor.set_sensitive(value)
        self.tc_display.widget.set_sensitive(value)
        self.pos_bar.widget.set_sensitive(value)      
        self.preset_label.set_sensitive(value)
        self.action_select.set_sensitive(value)
        self.action_label.set_sensitive(value)
        self.script_view.set_sensitive(value) 
        self.out_view.set_sensitive(value)       
        self.mark_in_info.set_sensitive(value)
        self.mark_out_info.set_sensitive(value)
        self.length_info.set_sensitive(value)
        self.out_folder.set_sensitive(value)
        self.encode_check_label.set_sensitive(value)
        self.encode_check.set_sensitive(value)
        self.encode_settings_button.set_sensitive(value)
        self.encode_desc.set_sensitive(value)
        self.frame_name.set_sensitive(value)
        self.extension_label.set_sensitive(value)       
        self.render_percentage.set_sensitive(value)
        self.render_status_info.set_sensitive(value)
        self.render_progress_bar.set_sensitive(value)
        self.stop_button.set_sensitive(False)
        self.render_button.set_sensitive(value)
        self.preview_button.set_sensitive(value)
        self.load_script.set_sensitive(value)
        self.save_script.set_sensitive(value)
        self.mark_in_label.set_sensitive(value)
        self.mark_out_label.set_sensitive(value)
        self.length_label.set_sensitive(value)
        self.out_label.set_sensitive(value)
        self.media_info.set_sensitive(value)
        self.present_event_box.set_sensitive(value)
        self.script_menu.set_sensitive(value)
 
        self.update_encode_sensitive()

#------------------------------------------------- global key listener
def _global_key_down_listener(widget, event):

    # Script view and frame name entry need their own key presses
    if _window.frame_name.has_focus() or _window.script_view.has_focus():
        return False
        
    # LEFT ARROW, prev frame
    if event.keyval == Gdk.KEY_Left:
        if (event.get_state() & Gdk.ModifierType.CONTROL_MASK):
            prev_pressed(-10)
            return True
        else:
            prev_pressed()
            return True
    # RIGHT ARROW, next frame
    if event.keyval == Gdk.KEY_Right:
        if (event.get_state() & Gdk.ModifierType.CONTROL_MASK):
            next_pressed(10)
            return True
        else:
            next_pressed()
            return True

    # DOWN ARROW, start
    if event.keyval == Gdk.KEY_Down:
        start_pressed()
        return True
        
    # UP ARROW, end
    if event.keyval == Gdk.KEY_Up:
        end_pressed()
        return True
                
    # I
    if event.keyval == Gdk.KEY_i:
        if (event.get_state() & Gdk.ModifierType.MOD1_MASK):
            to_mark_in_pressed()
            return True
        else:
            mark_in_pressed()
            return True
            
    if event.keyval == Gdk.KEY_I:
        if (event.get_state() & Gdk.ModifierType.MOD1_MASK):
            to_mark_in_pressed()
            return True
        else:
            mark_in_pressed()
            return True
    # O
    if event.keyval == Gdk.KEY_o:
        if (event.get_state() & Gdk.ModifierType.MOD1_MASK):
            to_mark_out_pressed()
            return True
        else:
            mark_out_pressed()
            return True
            
    if event.keyval == Gdk.KEY_O:
        if (event.get_state() & Gdk.ModifierType.MOD1_MASK):
            to_mark_out_pressed()
            return True
        else:
            mark_out_pressed()
            return True
        
    return False

#------------------------------------------------- render threads
class GmicPreviewRendererer(threading.Thread):

    def __init__(self, view_text):
        threading.Thread.__init__(self)
        self.view_text = view_text

    def run(self):
        start_time = time.time()
            
        try:
            # For the case the render fails
            shutil.copyfile(get_current_frame_file(), get_preview_file())
        except IOError:
            # We have failed to extract a png file from source file
            GLib.idle_add(self._update_buffer)
            return
    
        # Create command list and launch process.
        command_list = [editorstate.gmic_path, get_current_frame_file()]
        user_script_commands = self.view_text.split(" ")
        command_list.extend(user_script_commands)
        command_list.append("-output")
        command_list.append(get_preview_file())

        # Render preview and write log
        FLOG = open(userfolders.get_cache_dir() + "log_gmic_preview", 'w')
        p = subprocess.Popen(command_list, stdin=FLOG, stdout=FLOG, stderr=FLOG)
        p.wait()
        FLOG.close()
     
        # read log
        f = open(userfolders.get_cache_dir() + "log_gmic_preview", 'r')
        out = f.read()
        f.close()

        global _current_preview_surface
        _current_preview_surface = cairo.ImageSurface.create_from_png(get_preview_file())
    
        GLib.idle_add(self._preview_render_done_update, p, out, start_time)

    def _preview_render_done_update(self, p, out, start_time):
        _window.out_view.get_buffer().set_text(out + "Return code:" + str(p.returncode))

        render_time = time.time() - start_time
        time_str = "{0:.2f}".format(round(render_time,2))
        _window.preview_info.set_markup("<small>" + _("Preview for frame: ") + \
            utils.get_tc_string_with_fps(_player.current_frame(), _current_fps) + _(", render time: ") + time_str +  "</small>" )
            
        _window.preview_monitor.queue_draw()

    def _update_buffer():
        _window.out_view.get_buffer().set_text(_("Extracting PNG frames from this file failed!"))

            

class GmicEffectRendererer(threading.Thread):

    def __init__(self, user_script, out_folder):
        threading.Thread.__init__(self)
        self.user_script = user_script
        self.out_folder = out_folder

    def run(self):
        self.render_player = None
        self.frames_range_writer = None
        
        self.abort = False
        self.script_renderer = None
        
        # Delete old preview frames
        folder = get_render_frames_dir()
        for frame_file in os.listdir(folder):
            file_path = os.path.join(folder, frame_file)
            os.remove(file_path)
        
        # Render clip frames for range
        mark_in = _player.producer.mark_in
        mark_out = _player.producer.mark_out
        self.length = mark_out - mark_in + 1
        self.mark_in = mark_in
        self.mark_out = mark_out
        
        frame_name = _window.frame_name.get_text()

        self.frames_range_writer = gmicplayer.get_frames_range_writer_for_current_profile(_current_path, self.frames_update)
        self.frames_range_writer.write_frames(get_render_frames_dir() + "/", frame_name, mark_in, mark_out)

        if self.abort == True:
            return
        
        # Render effect for frames
        GLib.idle_add(self._show_percentage_and_fraction, "<small>" + _("Waiting for frames write to complete...") + "</small>", None)
         
        while len(os.listdir(folder)) != self.length:
            time.sleep(0.5)
        
        # Render frames with gmic script
        self.script_renderer = gmicplayer.FolderFramesScriptRenderer(   self.user_script, 
                                                                        folder,
                                                                        self.out_folder,
                                                                        frame_name,
                                                                        self.script_render_update_callback, 
                                                                        self.script_render_output_callback)
        self.script_renderer.write_frames()
        
        # Render video
        if _window.encode_check.get_active() == True:
            # Render consumer
            args_vals_list = toolsencoding.get_args_vals_list_for_render_data(_render_data)
            profile = mltprofiles.get_profile_for_index(_current_profile_index) 
            file_path = _render_data.render_dir + "/" +  _render_data.file_name  + _render_data.file_extension
            
            consumer = renderconsumer.get_mlt_render_consumer(file_path, profile, args_vals_list)
            
            # Render producer
            frame_file = self.out_folder + frame_name + "_0000.png"
            resource_name_str = utils.get_img_seq_resource_name(frame_file)
            resource_path = self.out_folder + "/" + resource_name_str
            producer = mlt.Producer(profile, str(resource_path))
            clip_frames = os.listdir(get_render_frames_dir())

            tractor = renderconsumer.get_producer_as_tractor(producer, len(clip_frames) - 1)

            self.render_player = renderconsumer.FileRenderPlayer("", tractor, consumer, 0, len(clip_frames) - 1)
            self.render_player.start()

            while self.render_player.stopped == False:
                if self.abort == True:
                    GLib.idle_add(self._show_percentage_and_fraction, "<small>" + _("Render stopped!") + "</small>", 0.0)
                    return
                
                fraction = self.render_player.get_render_fraction()
                update_info = _("Rendering video, ") + str(int(fraction * 100)) + _("% done")
                
                GLib.idle_add(self._show_percentage_and_fraction, update_info, fraction)
                
                time.sleep(0.3)

        GLib.idle_add(self._show_percentage_and_fraction, "<small>" + _("Render complete!") + "</small>", None)
        self.set_render_stopped_gui_state()
        
    def frames_update(self, frame):
        GLib.idle_add(self._do_frames_update, frame)

    def _do_frames_update(self, frame):
        if frame - self.mark_in < 0:
            frame = self.length # hack fix, producer suddenly changes the frame it thinks it is in
        else:
            frame = frame - self.mark_in # producer returns original clip frames
        
        update_info = _("Writing clip frame: ") + str(frame) + "/" +  str(self.length)

        _window.render_percentage.set_markup("<small>" + update_info + "</small>")
        _window.render_progress_bar.set_fraction(float(frame + 1)/float(self.length))

    def script_render_update_callback(self, frame_count):
        GLib.idle_add(self._do_script_render_update_callback_gui, frame_count)

    def _do_script_render_update_callback_gui(self, frame_count):
        update_info = _("Rendering frame: ") + str(frame_count) + "/" +  str(self.length)
        _window.render_percentage.set_markup("<small>" + update_info + "</small>")
        _window.render_progress_bar.set_fraction(float(frame_count)/float(self.length))

    def script_render_output_callback(self, p, out):
        GLib.idle_add(self._do_script_render_output_callback_gui, p, out)
        
    def _do_script_render_output_callback_gui(self, p, out):
        _window.out_view.get_buffer().set_text(out + "Return code:" + str(p.returncode))
        if p.returncode != 0:
            _window.render_percentage.set_text(_("Render error!"))
        else:
            _window.out_view.override_color((Gtk.StateFlags.NORMAL and Gtk.StateFlags.ACTIVE), None)

    def _show_percentage_and_fraction(self, percentage, fraction):
        _window.render_percentage.set_markup(percentage) #"<small>" + update_info + "</small>")
        if fraction != None:
            _window.render_progress_bar.set_fraction(fraction)

    def set_render_stopped_gui_state(self):
        GLib.idle_add(self._do_set_render_stopped_gui_state)
        
    def _do_set_render_stopped_gui_state(self):
        _window.render_progress_bar.set_fraction(0.0)
        _window.update_render_status_info()
        _window.stop_button.set_sensitive(False)
        _window.set_widgets_sensitive(True)
        _window.close_button.set_sensitive(True)
        _window.hamburger_launcher.widget.set_sensitive(True)
        _window.load_button.set_sensitive(True)
        if _window.encode_check.get_active() == True:
            _window.encode_settings_button.set_sensitive(True)
            _window.encode_desc.set_sensitive(True)

    def abort_render(self):
        self.abort = True

        if self.script_renderer != None:
             self.script_renderer.abort_rendering()

        self.shutdown()
                         
        _window.render_percentage.set_markup("<small>" + _("Render stopped!") + "</small>")
        self.set_render_stopped_gui_state()
        
    def shutdown(self):
        if self.frames_range_writer != None:
            self.frames_range_writer.shutdown()
        
        if self.render_player != None:
            self.render_player.shutdown()        
