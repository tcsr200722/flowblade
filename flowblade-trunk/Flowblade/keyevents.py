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
Module handles keyevents.
"""

from gi.repository import Gdk, Gtk

import re

import appconsts
import clipeffectseditor
import compositeeditor
import compositormodes
import glassbuttons
import gui
import editorpersistance
import editorstate
from editorstate import current_sequence
from editorstate import PLAYER
from editorstate import timeline_visible
import keyframeeditor
import kftoolmode
import medialog
import menuactions
import modesetting
import monitorevent
import movemodes
import shortcuts
import shortcutsquickeffects
import syncsplitevent
import render
import targetactions
import tlineaction
import tlinewidgets
import tlineypage
import trackaction
import trimmodes
import updater
import projectaction
import workflow

# TODO: We should consider integrating some parts of this with targetactions.py
# TODO:
# TODO: As of this writing, targetactions.py has a superset of targetable
# TODO: actions, as compared to keyevents.py, totally separate from any keyboard
# TODO: event handling. There are a few new named target actions in there that
# TODO: aren't available in here. There is also currently a lot code duplication
# TODO: between the two modules. See targetactions.py for more details.
# TODO:
# TODO: At a minimum, if you add or modify any of the key actions in here,
# TODO: please consider updating targetactions.py as well. Right now there
# TODO: is a lot of duplication between these modules, and often a change
# TODO: in one would warrant a change in the other.
# TODO:
# TODO: keyevents.py is all about handling key presses from the keyboard, and
# TODO: routing those events to trigger actions in various parts of the program.
# TODO:
# TODO: targetactions.py is basically a bunch of zero-argument functions with
# TODO: names based on the shortcut key names found here. It was created as part
# TODO: of the USB HID work, so that USB jog/shuttle devices could have their
# TODO: buttons target various actions within the program, without requiring
# TODO: each USB driver to directly make connections to a dozen different parts
# TODO: of the program to control it.
# TODO:
# TODO: So now we have two collections of shortcut key names which map to
# TODO: basically the same actions, but in a different way. I originally wanted
# TODO: to just use keyevents.py as the target for the USB driver actions, but
# TODO: couldn't use it directly since this module is intertwined with the
# TODO: main computer keyboard and its events.
# TODO:
# TODO: For now, I have integrated the new command targets from
# TODO: targetactions.py into keyevents.py, both for completeness, and also as
# TODO: a proof of concept as to how we might migrate some of the other code
# TODO: in here over to call targetactions.py
# TODO:
# TODO:   -- Nathan Rosenquist (@ratherlargerobot)
# TODO:      Feb 2022

# ------------------------------------- keyboard events
def key_down(widget, event):
    """
    Global key press listener.
    """

    # Handle ESCAPE.
    if event.keyval == Gdk.KEY_Escape:
        if editorstate.current_is_move_mode() == False:
            modesetting.set_default_edit_mode()
            return True
        elif gui.big_tc.get_visible_child_name() == "BigTCEntry":
            gui.big_tc.set_visible_child_name("BigTCDisplay")
            return True
    
    # Make Home and End work on name entry widget.
    # TODO: See which other components could benefit from this check.
    if render.widgets.file_panel.movie_name.has_focus():
        return False

    # Compositor editors keyevents
    was_handled = _handle_geometry_editor_keys(event)
    if was_handled:
        # Stop widget focus from travelling if arrow key pressed.
        gui.editor_window.window.emit_stop_by_name("key_press_event")
        return True

    was_handled = _handle_effects_editor_keys(event)
    if was_handled:
        # Stop widget focus from travelling if arrow key pressed
        gui.editor_window.window.emit_stop_by_name("key_press_event")
        return True

    # If timeline widgets are in focus timeline keyevents are available.
    if _timeline_has_focus():
        was_handled = _handle_tline_key_event(event)
        if was_handled:
            # Stop widget focus from travelling if arrow key pressed for next frame
            # by stopping signal.
            gui.editor_window.window.emit_stop_by_name("key_press_event")
        return was_handled
    
    # Insert shortcut keys need more focus then timeline shortcuts.
    # these may already have been handled in timeline focus events.
    was_handled = _handle_extended_monitor_focus_events(event)
    if was_handled:
        # Stop event handling here
        return True

    was_handled = _handle_configurable_global_events(event)
    if was_handled:
        return True

    # Pressing timeline button obviously leaves user expecting
    # to have focus in timeline.
    if gui.monitor_switch.widget.has_focus() and timeline_visible():
        _handle_tline_key_event(event)
        return True

    # Events that are available when monitor displays clip.
    if gui.monitor_switch.widget.has_focus() and (not timeline_visible()):
        _handle_clip_key_event(event)
        return True
    # Events that are available when monitor displays clip
    if gui.pos_bar.widget.is_focus() and (not timeline_visible()):
        _handle_clip_key_event(event)
        return True
        
    #  Handle non-timeline delete.
    if event.keyval == Gdk.KEY_Delete:
        return _handle_delete()

    # Home
    if event.keyval == Gdk.KEY_Home:
        if PLAYER().is_playing():
            monitorevent.stop_pressed()
        PLAYER().seek_frame(0)
        _move_to_beginning()
        return True

    # End
    if event.keyval == Gdk.KEY_End:
        if PLAYER().is_playing():
            monitorevent.stop_pressed()
        PLAYER().seek_end()
        _move_to_end()
        return True

    # Select all with CTRL + A in media panel.
    if event.keyval == Gdk.KEY_a:
        if (event.get_state() & Gdk.ModifierType.CONTROL_MASK):
            if gui.media_list_view.widget.has_focus() or gui.media_list_view.widget.get_focus_child() != None: 
                gui.media_list_view.select_all()
                return True

    if event.keyval == Gdk.KEY_F11:
        menuactions.toggle_fullscreen()
        return True

    # Key event was not handled here.
    return False
    
def _timeline_has_focus():
    if gui.editor_window.tool_selector != None and gui.editor_window.tool_selector.widget.has_focus():
        return True
    
    if(gui.tline_canvas.widget.has_focus()
       or gui.tline_column.widget.has_focus()
       or (gui.pos_bar.widget.has_focus() and timeline_visible())
       or gui.tline_scale.widget.has_focus()
       or glassbuttons.focus_group_has_focus(glassbuttons.DEFAULT_FOCUS_GROUP)):
        return True

    return False
    
def _handle_tline_key_event(event):
    """
    This is called when timeline widgets have focus and key is pressed.
    Returns True for handled key presses to stop those
    keyevents from going forward.
    """
    tool_was_selected = workflow.tline_tool_keyboard_selected(event)
    if tool_was_selected == True:
        return True
    

    action = _get_shortcut_action(event)
    prefs = editorpersistance.prefs


    if action == 'mark_in':
        monitorevent.mark_in_pressed()
        return True
    if action == 'to_mark_in':
        monitorevent.to_mark_in_pressed()
        return True
    if action == 'zoom_out':
        updater.zoom_out()
    if action == 'zoom_in':
        updater.zoom_in()
    if action == 'mark_out':
        monitorevent.mark_out_pressed()
        return True
    if action == 'to_mark_out':
        monitorevent.to_mark_out_pressed()
        return True
    if action == 'clear_mark_in':
        targetactions.clear_mark_in()
        return True
    if action == 'clear_mark_out':
        targetactions.clear_mark_out()
        return True
    if action == 'clear_io_marks':
        monitorevent.marks_clear_pressed()
        return True
    if action == 'play':
        targetactions.play()
        return True
    if action == 'stop':
        targetactions.stop()
        return True
    if action == 'play_pause':
        if PLAYER().is_playing():
            monitorevent.stop_pressed()
        else:
            monitorevent.play_pressed()
        return True
    if action == 'play_pause_loop_marks':
        if PLAYER().is_playing():
            monitorevent.stop_pressed()
        else:
            monitorevent.start_marks_looping()
        return True
    if action == 'display_clip_in_monitor':
        targetactions.display_clip_in_monitor()
        return True
    if action == 'display_sequence_in_monitor':
        targetactions.display_sequence_in_monitor()
        return True
    if action == 'switch_monitor':
        updater.switch_monitor_display()
        return True
    if action == 'add_marker':
        tlineaction.add_marker()
        return True    
    if action == 'cut':
        tlineaction.cut_pressed()
        return True
    if action == 'cut_all':
        tlineaction.cut_all_pressed()
        return True
    if action == 'sequence_split':
        tlineaction.sequence_split_pressed()
        return True
    if action == 'log_range':
        medialog.log_range_clicked()
        return True
    if action == 'toggle_ripple':
        gui.editor_window.toggle_trim_ripple_mode()
        return True
    if action == 'select_next':
        monitorevent.select_next_clip_for_filter_edit()
        return True
    if action == 'select_prev':
        monitorevent.select_prev_clip_for_filter_edit()
        return True
    if action == 'trim_start':
        tlineaction.trim_start_pressed()
        return True
    if action == 'trim_end':
        tlineaction.trim_end_pressed()
        return True
    if action == 'monitor_show_video':
        tlineaction.set_monitor_display_mode(appconsts.PROGRAM_OUT_MODE)
        return True
    if action == 'monitor_show_scope':
        tlineaction.set_monitor_display_mode(appconsts.VECTORSCOPE_MODE)
        return True
    if action == 'monitor_show_rgb':
        tlineaction.set_monitor_display_mode(appconsts.RGB_PARADE_MODE)
        return True
    if action == 'set_length':
        tlineaction.set_length_from_keyevent()
    if action == 'clear_sync_relation':
        syncsplitevent.clear_sync_relation_from_keyevent()
    if action == 'toggle_audio_mute':
        tlineaction.mute_clip_from_keyevent()
    if action == 'set_sync_relation':
        syncsplitevent.init_select_master_clip_from_keyevent()

    # Key bindings for keyboard trimming
    if action == 'toggle_track_output':
        trackaction.toggle_track_output()
        return True

    if editorstate.current_is_active_trim_mode() == True:
        if action == 'prev_frame':
            trimmodes.left_arrow_pressed((event.get_state() & Gdk.ModifierType.CONTROL_MASK))
            return True
        elif action == 'next_frame':
            trimmodes.right_arrow_pressed((event.get_state() & Gdk.ModifierType.CONTROL_MASK))
            return True
        elif action == 'enter_edit':
            trimmodes.enter_pressed()
            return True

    if editorstate.EDIT_MODE() == editorstate.OVERWRITE_MOVE: # is this what want, only in OVERWRITE_MOVE mode?
        if action == 'nudge_back':
            movemodes.nudge_selection(-1)
            return True
        elif action == 'nudge_forward':
            movemodes.nudge_selection(1)
            return True
        elif action == 'nudge_back_10':
            movemodes.nudge_selection(-10)
            return True
        elif action == 'nudge_forward_10':
            movemodes.nudge_selection(10)
            return True
    
    if editorstate.EDIT_MODE() == editorstate.MULTI_TRIM:
        modesetting.multitrim_mode_pressed()
        return True

    was_handled = shortcutsquickeffects.maybe_do_quick_shortcut_filter_add(event)
    if was_handled == True:
        return True

    # Key bindings for MOVE MODES and _NO_EDIT modes.
    if editorstate.current_is_move_mode() or editorstate.current_is_active_trim_mode() == False:
        if action == 'next_cut':
            if editorstate.timeline_visible():
                tline_frame = PLAYER().tracktor_producer.frame()
                frame = current_sequence().find_next_cut_frame(tline_frame)
                if frame != -1:
                    PLAYER().seek_frame(frame)
                    if editorpersistance.prefs.center_on_arrow_move == True:
                        updater.center_tline_to_current_frame()
                    return True
            else:
                monitorevent.up_arrow_seek_on_monitor_clip()
        if action == 'prev_cut':
            if editorstate.timeline_visible():
                tline_frame = PLAYER().tracktor_producer.frame()
                frame = current_sequence().find_prev_cut_frame(tline_frame)
                if frame != -1:
                    PLAYER().seek_frame(frame)
                    if editorpersistance.prefs.center_on_arrow_move == True:
                        updater.center_tline_to_current_frame()
                    return True
            else:
                 monitorevent.down_arrow_seek_on_monitor_clip()
                 return True
        # Apr-2017 - SvdB - Add different speeds for different modifiers
        # Allow user to select what speed belongs to what modifier, knowing that a combo of mods
        # will MULTIPLY all speeds.
        # Available: SHIFT_MASK LOCK_MASK CONTROL_MASK
        if action == 'prev_frame' or action == 'next_frame':
            if action == 'prev_frame':
                seek_amount = -1
            else:
                seek_amount = 1

            if (event.get_state() & Gdk.ModifierType.CONTROL_MASK):
                PLAYER().slowmo_seek_delta(seek_amount)
                return True
                
            if (event.get_state() & Gdk.ModifierType.SHIFT_MASK):
                seek_amount = seek_amount * prefs.ffwd_rev_shift

            if (event.get_state() & Gdk.ModifierType.LOCK_MASK):
                seek_amount = seek_amount * prefs.ffwd_rev_caps
            PLAYER().seek_delta(seek_amount)
            return True
        if action == '3_point_overwrite':
            tlineaction.three_point_overwrite_pressed()
            return True
        if action == 'overwrite_range':
            tlineaction.range_overwrite_pressed()
            return True
        if action == 'insert':
            if not (event.get_state() & Gdk.ModifierType.CONTROL_MASK):
                tlineaction.insert_button_pressed()
                return True
        if action == 'append':
            tlineaction.append_button_pressed()
            return True
        if action == 'append_from_bin':
            projectaction.append_selected_media_clips_into_timeline()
            return True
        if action == 'slower':
            monitorevent.j_pressed()
            return True
        if action == 'stop':
            monitorevent.k_pressed()
            return True
        if action == 'faster':
            monitorevent.l_pressed()
            return True
        if action == 'log_range':
            medialog.log_range_clicked()
            return True
        if action == 'resync':
            tlineaction.resync_track_button_pressed()
            return True
        if action == 'split_selected':
            tlineaction.split_audio_synched_button_pressed()
            return True
        if action == 'delete':
            if editorstate.EDIT_MODE() == editorstate.KF_TOOL:
                kftoolmode.delete_active_keyframe()
            else:
                # Clip selection and compositor selection are mutually exclusive, 
                # so max one one these will actually delete something.
                tlineaction.splice_out_button_pressed()
                compositormodes.delete_current_selection()
        if action == 'lift':
            tlineaction.lift_button_pressed()
            return True
        if action == 'to_start':
            if PLAYER().is_playing():
                monitorevent.stop_pressed()
            PLAYER().seek_frame(0)
            _move_to_beginning()
            return True
        if action == 'to_end':
            if PLAYER().is_playing():
                monitorevent.stop_pressed()
            PLAYER().seek_end()
            _move_to_end()
            return True
    else:
        if action == 'to_start':
            if PLAYER().is_playing():
                monitorevent.stop_pressed()
            gui.editor_window.tline_cursor_manager.set_default_edit_tool()
            PLAYER().seek_frame(0)
            _move_to_beginning()
            return True
        if action == 'to_end':
            if PLAYER().is_playing():
                monitorevent.stop_pressed()
            gui.editor_window.tline_cursor_manager.set_default_edit_tool()
            PLAYER().seek_end()
            _move_to_end()
            return True

    return False

def _handle_extended_monitor_focus_events(event):
    # This function was added to get a subset of events only to work when monitor has focus
    # Apr-2017 - SvdB - For keyboard shortcuts.
    action = _get_shortcut_action(event)

    # We're dropping monitor window in 2 window mode as part of timeline focus
    #    TODO:        gui.sequence_editor_b.has_focus() or
    #        gui.clip_editor_b.has_focus()):
    if not(gui.monitor_switch.widget.has_focus() or gui.pos_bar.widget.has_focus()):
        return False

    if action == '3_point_overwrite':
        tlineaction.three_point_overwrite_pressed()
        return True
    if action == 'overwrite_range':
        tlineaction.range_overwrite_pressed()
        return True
    if action == 'insert':
        tlineaction.insert_button_pressed()
        return True
    if action == 'append':
        tlineaction.append_button_pressed()
        return True
    if action == 'slower':
        monitorevent.j_pressed()
        return True
    if action == 'stop':
        monitorevent.k_pressed()
        return True
    if action == 'faster':
        monitorevent.l_pressed()
        return True
    if action == 'log_range':
        medialog.log_range_clicked()
        return True
    if action == 'display_clip_in_monitor':
        targetactions.display_clip_in_monitor()
        return True
    if action == 'display_sequence_in_monitor':
        targetactions.display_sequence_in_monitor()
        return True
    if action == 'switch_monitor':
        updater.switch_monitor_display()
        return True
    if action == 'append_from_bin':
        projectaction.append_selected_media_clips_into_timeline()
        return True

    tool_was_selected = workflow.tline_tool_keyboard_selected(event)
    if tool_was_selected == True:
        return True

    return False
        
# Apr-2017 - SvdB
def _get_shortcut_action(event):
    # Get the name of the key pressed.
    key_name = Gdk.keyval_name(event.keyval).lower()

    # Check if this key is in the dictionary.
    state = event.get_state()
    # Now we have a key and a key state we need to check if it is a shortcut.
    # If it IS a shortcut we need to determine what action to take.
    if key_name in shortcuts._keyboard_actions:
        # Now get the associated dictionary
        _secondary_dict = shortcuts._keyboard_actions[key_name]
        # In order to check for all available combinations of Ctrl+Alt etc (CTRL+ALT should be the same as ALT_CTRL)
        # we do a SORT on the string. So both CTRL+ALT and ALT+CTRL will become +ACLLRTT and can be easily compared.
        modifier = ""
        if state & Gdk.ModifierType.CONTROL_MASK:
            modifier = "CTRL"
        if state & Gdk.ModifierType.MOD1_MASK:
            if modifier != "":
                modifier = modifier + "+"
            modifier = modifier + "ALT"
        if state & Gdk.ModifierType.SHIFT_MASK:
            if modifier != "":
                modifier = modifier + "+"
            modifier = modifier + "SHIFT"
        # CapsLock is used as an equivalent to SHIFT, here
        if state & Gdk.ModifierType.LOCK_MASK:
            if modifier != "":
                modifier = modifier + "+"
            modifier = modifier + "SHIFT"
        # Set to None if no modifier found
        if modifier == "":
            modifier = 'None'
        try:
            action = _secondary_dict[''.join(sorted(re.sub(r'[\s]','',modifier.lower())))]
        except:
            try:
                action = _secondary_dict[''.join(sorted(re.sub(r'[\s]','','Any'.lower())))]
            except:
                action = 'None'
        return action
    # We didn't find an action, so return nothing.
    return 'None'

def _handle_configurable_global_events(event):
    action = _get_shortcut_action(event)
    if action == 'tline_page_up':
        tlineypage.page_up_key()
        return True
    if action == 'tline_page_down':
        tlineypage.page_down_key()
        return True
    if action == 'open_next':
        projectaction.open_next_media_item_in_monitor()
        return True
    if action == 'open_prev':
        projectaction.open_prev_media_item_in_monitor()
        return True
    if action == "append_from_bin":
        if gui.media_list_view.widget.has_focus() or gui.media_list_view.widget.get_focus_child() != None: 
            projectaction.append_selected_media_clips_into_timeline()
            return True
    if action == "move_media":
        gui.media_list_view.init_move()
    if action == 'monitor_show_video':
        tlineaction.set_monitor_display_mode(appconsts.PROGRAM_OUT_MODE)
        return True
    if action == 'monitor_show_scope':
        tlineaction.set_monitor_display_mode(appconsts.VECTORSCOPE_MODE)
        return True
    if action == 'monitor_show_rgb':
        tlineaction.set_monitor_display_mode(appconsts.RGB_PARADE_MODE)
        return True

    return False
    
def _handle_clip_key_event(event):
    # Key bindings for MOVE MODES
    if editorstate.current_is_move_mode():
        action = _get_shortcut_action(event)
        # Apr-2017 - SvdB - Add different speeds for different modifiers
        # Allow user to select what speed belongs to what modifier, knowing that a combo of mods
        # will MULTIPLY all speeds.
        # Available: SHIFT_MASK LOCK_MASK CONTROL_MASK.
        
        prefs = editorpersistance.prefs
        if action == 'prev_frame' or action == 'next_frame':
            if action == 'prev_frame':
                seek_amount = -1
            else:
                seek_amount = 1
            
            if (event.get_state() & Gdk.ModifierType.CONTROL_MASK):
                PLAYER().slowmo_seek_delta(seek_amount)
                return True
                
            if (event.get_state() & Gdk.ModifierType.SHIFT_MASK):
                seek_amount = seek_amount * prefs.ffwd_rev_shift
            if (event.get_state() & Gdk.ModifierType.LOCK_MASK):
                seek_amount = seek_amount * prefs.ffwd_rev_caps
            PLAYER().seek_delta(seek_amount)
            return True

        if action == 'next_cut':
            if editorstate.timeline_visible():
                tline_frame = PLAYER().tracktor_producer.frame()
                frame = current_sequence().find_next_cut_frame(tline_frame)
                if frame != -1:
                    PLAYER().seek_frame(frame)
                    if editorpersistance.prefs.center_on_arrow_move == True:
                        updater.center_tline_to_current_frame()
                    return True
            else:
                 monitorevent.up_arrow_seek_on_monitor_clip()
                 return True
        if action == 'prev_cut':
            if editorstate.timeline_visible():
                tline_frame = PLAYER().tracktor_producer.frame()
                frame = current_sequence().find_prev_cut_frame(tline_frame)
                if frame != -1:
                    PLAYER().seek_frame(frame)
                    if editorpersistance.prefs.center_on_arrow_move == True:
                        updater.center_tline_to_current_frame()  
                    return True
            else:
                 monitorevent.down_arrow_seek_on_monitor_clip()
                 return True
        if action == 'play':
            targetactions.play()
            return True
        if action == 'stop':
            targetactions.stop()
            return True
        if action == 'play_pause':
            if PLAYER().is_playing():
                monitorevent.stop_pressed()
            else:
                monitorevent.play_pressed()
            return True
        if action == 'play_pause_loop_marks':
            if PLAYER().is_playing():
                monitorevent.stop_pressed()
            else:
                monitorevent.start_marks_looping()
            return True
        if action == 'mark_in':
            monitorevent.mark_in_pressed()
            return True
        if action == 'to_mark_in':
            monitorevent.to_mark_in_pressed()
            return True
        if action == 'mark_out':
            monitorevent.mark_out_pressed()
            return True
        if action == 'to_mark_out':
            monitorevent.to_mark_out_pressed()
            return True
        if action == 'clear_mark_in':
            targetactions.clear_mark_in()
            return True
        if action == 'clear_mark_out':
            targetactions.clear_mark_out()
            return True
        if action == 'clear_io_marks':
            monitorevent.marks_clear_pressed()
            return True

def _handle_delete():
    # Delete media file
    if gui.media_list_view.widget.get_focus_child() != None:
        projectaction.delete_media_files()
        return True

    # Delete bin
    if gui.bin_list_view.get_focus_child() != None:
        if gui.bin_list_view.text_rend_1.get_property("editing") == True:
            return False
        projectaction.delete_selected_bin()
        return True

    # Delete sequence
    if gui.sequence_list_view.get_focus_child() != None:
        if gui.sequence_list_view.text_rend_1.get_property("editing") == True:
            return False
        projectaction.delete_selected_sequence()
        return True

    # Delete media log event
    if gui.editor_window.media_log_events_list_view.get_focus_child() != None:
        medialog.delete_selected()
        return True
    
    focus_editor = _get_focus_keyframe_editor(compositeeditor.keyframe_editor_widgets)
    if focus_editor != None:
        focus_editor.delete_pressed()
        return True

    focus_editor = _get_focus_keyframe_editor(clipeffectseditor.keyframe_editor_widgets)
    if focus_editor != None:
        focus_editor.delete_pressed()
        return True

    return False

def _handle_geometry_editor_keys(event):
    if compositeeditor.keyframe_editor_widgets != None:
        for kfeditor in compositeeditor.keyframe_editor_widgets:
            if kfeditor.get_focus_child() != None:
                if kfeditor.__class__ == keyframeeditor.GeometryEditor or \
                kfeditor.__class__ == keyframeeditor.RotatingGeometryEditor:
                    # Apr-2017 - SvdB - For keyboard shortcuts. I have NOT changed the arrow keys for
                    # the kfeditor action. That didn't seem appropriate
                    action = _get_shortcut_action(event)
                    if ((event.keyval == Gdk.KEY_Left) 
                        or (event.keyval == Gdk.KEY_Right)
                        or (event.keyval == Gdk.KEY_Up)
                        or (event.keyval == Gdk.KEY_Down)):
                        kfeditor.arrow_edit(event.keyval, (event.get_state() & Gdk.ModifierType.CONTROL_MASK), (event.get_state() & Gdk.ModifierType.SHIFT_MASK))
                        return True
                    if event.keyval == Gdk.KEY_plus:
                        pass # not impl
                    if action == 'play':
                        targetactions.play()
                        return True
                    if action == 'stop':
                        targetactions.stop()
                        return True
                    if action == 'play_pause':
                        if PLAYER().is_playing():
                            monitorevent.stop_pressed()
                        else:
                            monitorevent.play_pressed()
                        return True
                    if action == 'play_pause_loop_marks':
                        if PLAYER().is_playing():
                            monitorevent.stop_pressed()
                        else:
                            monitorevent.start_marks_looping()
                        return True
    return False

def _handle_effects_editor_keys(event):
    action = _get_shortcut_action(event)
    focus_editor = _get_focus_keyframe_editor(clipeffectseditor.keyframe_editor_widgets)

                        
    if focus_editor != None:
        if focus_editor.get_focus_child() != None:
            if focus_editor.__class__ == keyframeeditor.FilterRectGeometryEditor or \
                focus_editor.__class__ == keyframeeditor.FilterRotatingGeometryEditor or \
                focus_editor.__class__ == keyframeeditor.GeometryNoKeyframes:
                if ((event.keyval == Gdk.KEY_Left) 
                    or (event.keyval == Gdk.KEY_Right)
                    or (event.keyval == Gdk.KEY_Up)
                    or (event.keyval == Gdk.KEY_Down)):
                    focus_editor.arrow_edit(event.keyval, (event.get_state() & Gdk.ModifierType.CONTROL_MASK), (event.get_state() & Gdk.ModifierType.SHIFT_MASK))
                    return True
        if action == 'play':
            targetactions.play()
            return True
        if action == 'stop':
            targetactions.stop()
            return True
        if action == 'play_pause':
            if PLAYER().is_playing():
                monitorevent.stop_pressed()
            else:
                monitorevent.play_pressed()
            return True
        if action == 'play_pause_loop_marks':
            if PLAYER().is_playing():
                monitorevent.stop_pressed()
            else:
                monitorevent.start_marks_looping()
            return True
        if action == 'prev_frame' or action == 'next_frame':
            prefs = editorpersistance.prefs
            if action == 'prev_frame':
                seek_amount = -1
            else:
                seek_amount = 1
            
            if (event.get_state() & Gdk.ModifierType.CONTROL_MASK):
                PLAYER().slowmo_seek_delta(seek_amount)
                return True
                
            if (event.get_state() & Gdk.ModifierType.SHIFT_MASK):
                seek_amount = seek_amount * prefs.ffwd_rev_shift
            if (event.get_state() & Gdk.ModifierType.LOCK_MASK):
                seek_amount = seek_amount * prefs.ffwd_rev_caps
            PLAYER().seek_delta(seek_amount)
            return True
        
    return False

def _get_focus_keyframe_editor(keyframe_editor_widgets):
    if keyframe_editor_widgets == None:
        return None
    for kfeditor in keyframe_editor_widgets:
        if kfeditor.get_focus_child() != None:
           return kfeditor
    return None

def _move_to_beginning():
    tlinewidgets.pos = 0
    updater.repaint_tline()
    updater.update_tline_scrollbar()
    
def _move_to_end():
    updater.repaint_tline()
    updater.update_tline_scrollbar()

# ----------------------------------------------------------------------- COPY PASTE ACTION FORWARDING
def cut_action():
    if _timeline_has_focus() == False:
        # Try to cut text to clipboard because user pressed CTRL + X.
        if gui.media_list_view.widget.get_focus_child() != None:
            projectaction.cut_media_files()
            return True
                    
        # Try to extract text to clipboard because user pressed CTRL + C.
        copy_source = gui.editor_window.window.get_focus()
        try:
            display = Gdk.Display.get_default()
            cb = Gtk.Clipboard.get_default(display)
            copy_source.get_buffer().cut_clipboard(cb, True)
            return True
        except:# selected widget was not a Gtk.Editable that can provide text to clipboard.
            return False
    else:
        tlineaction.do_timeline_objects_copy(False)
        return True
        
def copy_action():
    if _timeline_has_focus() == False:
        filter_kf_editor = _get_focus_keyframe_editor(clipeffectseditor.keyframe_editor_widgets)
        geom_kf_editor = _get_focus_keyframe_editor(compositeeditor.keyframe_editor_widgets)
        if filter_kf_editor != None:
            value = filter_kf_editor.get_copy_kf_value()
            save_data = (appconsts.COPY_PASTE_KEYFRAME_EDITOR_KF_DATA, (value, filter_kf_editor))
            editorstate.set_copy_paste_objects(save_data) 
            return True
        elif geom_kf_editor != None:
            value = geom_kf_editor.get_copy_kf_value() 
            save_data = (appconsts.COPY_PASTE_GEOMETRY_EDITOR_KF_DATA, (value, geom_kf_editor))
            editorstate.set_copy_paste_objects(save_data)
            return True
        else:
            # Try to extract text to clipboard because user pressed CTRL + C.
            copy_source = gui.editor_window.window.get_focus()
            try:
                display = Gdk.Display.get_default()
                cb = Gtk.Clipboard.get_default (display)
                copy_source.get_buffer().copy_clipboard(cb)
                return True
            except:# selected widget was not a Gtk.Editable that can provide text to clipboard.
                return False
    else:
        tlineaction.do_timeline_objects_copy()
        return True

def paste_action():
    if _timeline_has_focus() == False:
        copy_paste_object = editorstate.get_copy_paste_objects()
        if copy_paste_object == None:
            _attempt_default_paste()
            return False
        data_type, paste_data = editorstate.get_copy_paste_objects()
        if data_type == appconsts.COPY_PASTE_KEYFRAME_EDITOR_KF_DATA:
            value, kf_editor = paste_data
            kf_editor.paste_kf_value(value)
            return True
        elif data_type == appconsts.COPY_PASTE_GEOMETRY_EDITOR_KF_DATA:
            value, geom_editor = paste_data
            geom_editor.paste_kf_value(value)
            return True
        elif data_type == appconsts.CUT_PASTE_MEDIA_ITEMS:
            projectaction.paste_media_files()
            return True
        
        return False
    else:
        tlineaction.do_timeline_objects_paste()
        _attempt_default_paste()
        return True

def _attempt_default_paste():
    # Try to extract text to clipboard because user pressed CTRL + C.
    paste_target = gui.editor_window.window.get_focus()
    try:
        display = Gdk.Display.get_default()
        clipboard = Gtk.Clipboard.get_default(display)
        paste_target.get_buffer().paste_clipboard(clipboard, None, True)
        return True
    except:# selected widget cannot be pasted into
        return False
                

def change_single_shortcut(code, event, shortcut_label):
    key_val_name = Gdk.keyval_name(event.keyval).lower()
    
    mods_list = []
    state = event.get_state()
    if state & Gdk.ModifierType.CONTROL_MASK:
        mods_list.append("CTRL")
    if state & Gdk.ModifierType.MOD1_MASK:
        mods_list.append("ALT")
        
    if state & Gdk.ModifierType.SHIFT_MASK:
        mods_list.append("SHIFT")
    elif state & Gdk.ModifierType.LOCK_MASK:     # CapsLock is used as an equivalent to SHIFT.
        mods_list.append("SHIFT")

    shortcut_info_str = shortcuts.get_shortcut_info_for_keyname_and_modlist(key_val_name, mods_list)
    if shortcuts.is_blocked_shortcut(key_val_name, mods_list):
        return shortcut_info_str

    shortcut_label.set_text(shortcut_info_str)

    shortcuts.change_custom_shortcut(code, key_val_name, mods_list)
    shortcuts.set_keyboard_shortcuts()

    return None
