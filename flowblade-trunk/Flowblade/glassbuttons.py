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

import cairo
import math

import cairoarea
import editorpersistance
import gui
import guiutils
import respaths

BUTTONS_GRAD_STOPS = [   (1, 1, 1, 1, 0.2),
                        (0.8, 1, 1, 1, 0),
                        (0.51, 1, 1, 1, 0),
                        (0.50, 1, 1, 1, 0.25),
                        (0, 1, 1, 1, 0.4)]

BUTTONS_PRESSED_GRAD_STOPS = [(1, 0.7, 0.7, 0.7, 1),
                             (0, 0.5, 0.5, 0.5, 1)]

LINE_GRAD_STOPS = [ (1, 0.66, 0.66, 0.66, 1),
                            (0.95, 0.7, 0.7, 0.7, 1),
                            (0.65, 0.3, 0.3, 0.3, 1),
                            (0, 0.64, 0.64, 0.64, 1)]

BUTTON_NOT_SENSITIVE_GRAD_STOPS = [(1, 0.9, 0.9, 0.9, 0.7),
                                    (0, 0.9, 0.9, 0.9, 0.7)]

CORNER_DIVIDER = 5

MB_BUTTONS_WIDTH = [200]
MB_BUTTONS_HEIGHT = [23]
MB_BUTTON_HEIGHT = [22]
MB_BUTTON_WIDTH = [30]
MB_BUTTON_Y = 4
MB_BUTTON_IMAGE_Y = 6

GMIC_BUTTONS_WIDTH = 250

M_PI = math.pi

NO_HIT = -1

# Focus groups are used to test if one widget in the group of buttons widgets has keyboard focus
DEFAULT_FOCUS_GROUP = "default_focus_group"
focus_groups = {DEFAULT_FOCUS_GROUP:[]}



class AbstractGlassButtons:

    def __init__(self, button_width, button_height, button_y, widget_width, widget_height):
        # Create widget and connect listeners
        self.widget = cairoarea.CairoDrawableArea2( widget_width,
                                                    widget_height,
                                                    self._draw)
        self.widget.press_func = self._press_event
        self.widget.motion_notify_func = self._motion_notify_event
        self.widget.release_func = self._release_event

        self.pressed_callback_funcs = None # set later
        self.released_callback_funcs = None # set later

        self.pressed_button = -1

        self.degrees = M_PI / 180.0

        self.button_width = button_width
        self.button_height = button_height
        self.button_y = button_y
        self.button_x = 0 # set when first allocation known by extending class

        self.icons = []
        self.image_x = []
        self.image_y = []
        self.sensitive = [] # not used currently
        
        self.prelight_icons = []
        self.prelight_index = -1
        
        if editorpersistance.prefs.buttons_style == editorpersistance.GLASS_STYLE:
            self.glass_style = True
        else:
            self.glass_style = False

        self.no_decorations = False

        # Dark theme comes with flat buttons
        self.dark_theme = False

        self.glass_style = False
        self.dark_theme = True

        self.draw_button_gradients = True # old code artifact, remove (set False at object creation site to kill all gradients)

    def _set_button_draw_consts(self, x, y, width, height):
        aspect = 1.0
        corner_radius = height / CORNER_DIVIDER
        radius = corner_radius / aspect

        self._draw_consts = (x, y, width, height, aspect, corner_radius, radius)

    def set_sensitive(self, value):
        self.sensitive = []
        for i in self.icons:
            self.sensitive.append(value)

    def _round_rect_path(self, cr):
        x, y, width, height, aspect, corner_radius, radius = self._draw_consts
        degrees = self.degrees

        cr.new_sub_path()
        cr.arc (x + width - radius, y + radius, radius, -90 * degrees, 0 * degrees)
        cr.arc (x + width - radius, y + height - radius, radius, 0 * degrees, 90 * degrees)
        cr.arc (x + radius, y + height - radius, radius, 90 * degrees, 180 * degrees)
        cr.arc (x + radius, y + radius, radius, 180 * degrees, 270 * degrees)
        cr.close_path ()

    def _press_event(self, event):
        print("_press_event not impl")

    def _motion_notify_event(self, x, y, state):
        print("_motion_notify_event not impl")

    def _release_event(self, event):
        print("_release_event not impl")

    def _leave_notify_event(self, event):
        print("_leave_notify_event not impl")
        
    def _enter_notify_event(self, event):
        print("_enter_notify_event not impl")
        
    def _draw(self, event, cr, allocation):
        print("_draw not impl")

    def _get_hit_code(self, x, y):
        button_x = self.button_x
        for i in range(0, len(self.icons)):
            if ((x >= button_x) and (x <= button_x + self.button_width)
                and (y >= self.button_y) and (y <= self.button_y + self.button_height)):
                    if self.sensitive[i] == True:
                        return i
            button_x += self.button_width

        return NO_HIT

    def _draw_buttons(self, cr, w, h):
        # Width of buttons group
        buttons_width = self.button_width * len(self.icons)

        if self.no_decorations == True:
            x = self.button_x
            for i in range(0, len(self.icons)):
                icon = self.icons[i]
                if self.prelight_index == i:
                    icon = self.prelight_icons[i]
                cr.set_source_surface(icon, x + self.image_x[i], self.image_y[i])
                cr.paint()
                x += self.button_width

            return

        # Line width for all strokes
        cr.set_line_width(1.0)

        # bg
        self._set_button_draw_consts(self.button_x + 0.5, self.button_y + 0.5, buttons_width, self.button_height + 1.0)
        self._round_rect_path(cr)
        r, g, b, a  = gui.get_bg_color()
        if self.draw_button_gradients:
            if self.glass_style == True:
                cr.set_source_rgb(0.75, 0.75, 0.75)
                cr.fill_preserve()
            else:
                grad = cairo.LinearGradient (self.button_x, self.button_y, self.button_x, self.button_y + self.button_height)
                if self.dark_theme == False:
                    grad.add_color_stop_rgba(1, r - 0.1, g - 0.1, b - 0.1, 1)
                    grad.add_color_stop_rgba(0, r + 0.1, g + 0.1, b + 0.1, 1)
                else:
                    grad.add_color_stop_rgba(1, r + 0.04, g + 0.04, b + 0.04, 1)
                    grad.add_color_stop_rgba(0, r + 0.07, g + 0.07, b + 0.07, 1)

                cr.set_source(grad)
                cr.fill_preserve()

        # Pressed button gradient
        if self.pressed_button > -1:
            if self.draw_button_gradients:
                grad = cairo.LinearGradient (self.button_x, self.button_y, self.button_x, self.button_y + self.button_height)
                if self.glass_style == True:
                    for stop in BUTTONS_PRESSED_GRAD_STOPS:
                        grad.add_color_stop_rgba(*stop)
                else:
                    grad = cairo.LinearGradient (self.button_x, self.button_y, self.button_x, self.button_y + self.button_height)
                    grad.add_color_stop_rgba(1, r - 0.3, g - 0.3, b - 0.3, 1)
                    grad.add_color_stop_rgba(0, r - 0.1, g - 0.1, b - 0.1, 1)
            else:
                    grad = cairo.LinearGradient (self.button_x, self.button_y, self.button_x, self.button_y + self.button_height)
                    grad.add_color_stop_rgba(1, r - 0.3, g - 0.3, b - 0.3, 1)
                    grad.add_color_stop_rgba(0, r - 0.3, g - 0.3, b - 0.3, 1)
            cr.save()
            cr.set_source(grad)
            cr.clip()
            cr.rectangle(self.button_x + self.pressed_button * self.button_width, self.button_y, self.button_width, self.button_height)
            cr.fill()
            cr.restore()

        # Icons and sensitive gradient
        grad = cairo.LinearGradient (self.button_x, self.button_y, self.button_x, self.button_y + self.button_height)
        for stop in BUTTON_NOT_SENSITIVE_GRAD_STOPS:
            grad.add_color_stop_rgba(*stop)
        x = self.button_x
        for i in range(0, len(self.icons)):
            icon = self.icons[i]
            cr.set_source_surface(icon, x + self.image_x[i], self.image_y[i])
            cr.paint()
            if self.sensitive[i] == False:
                cr.save()
                self._round_rect_path(cr)
                cr.set_source(grad)
                cr.clip()
                cr.rectangle(x, self.button_y, self.button_width, self.button_height)
                cr.fill()
                cr.restore()
            x += self.button_width

        if self.glass_style == True and self.draw_button_gradients:
            # Glass gradient
            self._round_rect_path(cr)
            grad = cairo.LinearGradient (self.button_x, self.button_y, self.button_x, self.button_y + self.button_height)
            for stop in BUTTONS_GRAD_STOPS:
                grad.add_color_stop_rgba(*stop)
            cr.set_source(grad)
            cr.fill()
        else:
            pass

        if self.dark_theme != True:
            # Round line
            grad = cairo.LinearGradient (self.button_x, self.button_y, self.button_x, self.button_y + self.button_height)
            for stop in LINE_GRAD_STOPS:
                grad.add_color_stop_rgba(*stop)
            cr.set_source(grad)
            self._set_button_draw_consts(self.button_x + 0.5, self.button_y + 0.5, buttons_width, self.button_height)
            self._round_rect_path(cr)
            cr.stroke()

        if self.dark_theme == True:
            cr.set_source_rgb(0,0,0)

        # Vert lines
        x = self.button_x
        for i in range(0, len(self.icons)):
            if (i > 0) and (i < len(self.icons)):
                cr.move_to(x + 0.5, self.button_y)
                cr.line_to(x + 0.5, self.button_y + self.button_height)
                cr.stroke()
            x += self.button_width

    def show_prelight_icons(self):
        self.prelight_icons = []
        for icon in self.icons:
            surface_prelight = cairo.ImageSurface(cairo.FORMAT_ARGB32, icon.get_width(), icon.get_height())
            cr = cairo.Context(surface_prelight)
            cr.set_source_surface(icon, 0, 0)
            cr.rectangle(0, 0, icon.get_width(), icon.get_height())
            cr.fill()
            
            cr.set_operator(cairo.Operator.ATOP)
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.5)
            cr.rectangle(0, 0, icon.get_width(), icon.get_height())
            cr.fill()
            
            self.prelight_icons.append(surface_prelight)

        self.widget.leave_notify_func = self._leave_notify_event
        self.widget.enter_notify_func = self._enter_notify_event


class PlayerButtons(AbstractGlassButtons):

    def __init__(self):
        # Aug-2019 - SvdB - BB - Multiple changes - size_ind, size_adj, get_cairo_image
        size_ind = 0
        size_adj = 1
        prefs = editorpersistance.prefs

        AbstractGlassButtons.__init__(self, MB_BUTTON_WIDTH[size_ind], MB_BUTTON_HEIGHT[size_ind], MB_BUTTON_Y, MB_BUTTONS_WIDTH[size_ind], MB_BUTTONS_HEIGHT[size_ind] - 2)

        # Force no decorations for player buttons, this cannot be made to work.
        self.no_decorations = True 

        play_pause_icon = guiutils.get_cairo_image("play_pause_s")
        play_icon = guiutils.get_cairo_image("play_2_s")
        stop_icon = guiutils.get_cairo_image("stop_s")
        next_icon = guiutils.get_cairo_image("next_frame_s")
        prev_icon = guiutils.get_cairo_image("prev_frame_s")
        # ------------------------------timeline_start_end_button
        start_icon = guiutils.get_cairo_image("to_start") #  go to start
        end_icon = guiutils.get_cairo_image("to_end") #  go to end
        # ------------------------------timeline_start_end_button
        mark_in_icon = guiutils.get_cairo_image("mark_in_s")
        mark_out_icon = guiutils.get_cairo_image("mark_out_s")
        marks_clear_icon = guiutils.get_cairo_image("marks_clear_s")
        to_mark_in_icon = guiutils.get_cairo_image("to_mark_in_s")
        to_mark_out_icon = guiutils.get_cairo_image("to_mark_out_s")

        # Jul-2016 - SvdB - For play/pause button
        if (editorpersistance.prefs.play_pause == True):
            # ------------------------------timeline_start_end_button
            if (editorpersistance.prefs.timeline_start_end == True):
                self.icons = [start_icon, end_icon, prev_icon, next_icon, play_pause_icon,
                          mark_in_icon, mark_out_icon,
                          marks_clear_icon, to_mark_in_icon, to_mark_out_icon]
                #  go to start end add 5*size_adj, 5*size_adj,
                self.image_x = [5*size_adj, 5*size_adj, 5*size_adj, 7*size_adj, 5*size_adj, 3*size_adj, 11*size_adj, 2*size_adj, 7*size_adj, 6*size_adj]
            else:
                self.icons = [prev_icon, next_icon, play_pause_icon,
                          mark_in_icon, mark_out_icon,
                          marks_clear_icon, to_mark_in_icon, to_mark_out_icon]
                self.image_x = [ 5*size_adj, 7*size_adj, 11*size_adj, 3*size_adj, 11*size_adj, 2*size_adj, 7*size_adj, 0*size_adj]
        else:
            #  go to start end
            if (editorpersistance.prefs.timeline_start_end == True):
                self.icons = [start_icon, end_icon, prev_icon, next_icon, play_icon, stop_icon,
                              mark_in_icon, mark_out_icon,
                              marks_clear_icon, to_mark_in_icon, to_mark_out_icon]
                #  go to start end add 5*size_adj, 5*size_adj,
                self.image_x = [7*size_adj, 7*size_adj, 5*size_adj, 7*size_adj, 20*size_adj, 10*size_adj, 0*size_adj, 6*size_adj, 2*size_adj, 10*size_adj, 4*size_adj]
            else:
                self.icons = [prev_icon, next_icon, play_icon, stop_icon,
                              mark_in_icon, mark_out_icon,
                              marks_clear_icon, to_mark_in_icon, to_mark_out_icon]
                self.image_x = [5*size_adj, 7*size_adj, 20*size_adj, 10*size_adj, 0*size_adj, 6*size_adj, 2*size_adj, 10*size_adj, 4*size_adj]
            # ------------------------------End of timeline_start_end_button

        for i in range(0, len(self.icons)):
            self.image_y.append(MB_BUTTON_IMAGE_Y - 6)
        
        self.pressed_callback_funcs = None # set using set_callbacks()

        self.set_sensitive(True)

        focus_groups[DEFAULT_FOCUS_GROUP].append(self.widget)

        self.show_prelight_icons()

    def set_normal_sensitive_pattern(self):
        self.set_sensitive(True)
        self.widget.queue_draw()

    # ------------------------------------------------------------- mouse events
    def _press_event(self, event):
        """
        Mouse button callback
        """
        self.pressed_button = self._get_hit_code(event.x, event.y)
        if self.pressed_button >= 0 and self.pressed_button < len(self.icons):
            callback_func = self.pressed_callback_funcs[self.pressed_button] # index is set to match at editorwindow.py where callback func list is created
            callback_func()
        self.widget.queue_draw()

    def _motion_notify_event(self, x, y, state):
        """
        Mouse move callback
        """
        button_under = self._get_hit_code(x, y)
        if self.pressed_button != button_under: # pressed button is released
            self.pressed_button = NO_HIT

        if len(self.prelight_icons) > 0:
            self.prelight_index = button_under
            
        self.widget.queue_draw()

    def _release_event(self, event):
        """
        Mouse release callback
        """
        self.pressed_button = -1
        self.widget.queue_draw()

    def _leave_notify_event(self, event):
        self.prelight_index = -1
        self.widget.queue_draw()

    def _enter_notify_event(self, event):
        self.prelight_index = -1
        
    def set_callbacks(self, pressed_callback_funcs):
        self.pressed_callback_funcs = pressed_callback_funcs

    # ---------------------------------------------------------------- painting
    def _draw(self, event, cr, allocation):
        x, y, w, h = allocation
        self.allocation = allocation

        mid_x = w // 2
        buttons_width = self.button_width * len(self.icons)
        # Jul-2016 - SvdB - No changes made here, but because of the calculation of button_x the row of buttons is slightly moved right if play/pause
        # is enabled. This could be solved by setting self.button_x = 1, if wished.
        self.button_x = mid_x - (buttons_width // 2)
        self._draw_buttons(cr, w, h)

class PlayerButtonsCompact(AbstractGlassButtons):

    def __init__(self):
        # Aug-2019 - SvdB - BB - Multiple changes - size_ind, size_adj, get_cairo_image
        size_ind = 0
        AbstractGlassButtons.__init__(self, MB_BUTTON_WIDTH[size_ind], MB_BUTTON_HEIGHT[size_ind], MB_BUTTON_Y, MB_BUTTONS_WIDTH[size_ind], MB_BUTTONS_HEIGHT[size_ind] - 2)

        # Force no decorations for player buttons, this cannot be made to work.
        self.no_decorations = True 

        self.play_icon = guiutils.get_cairo_image("play_2_s")
        self.stop_icon = guiutils.get_cairo_image("stop_s")
        self.next_icon = guiutils.get_cairo_image("next_frame_s")
        self.prev_icon = guiutils.get_cairo_image("prev_frame_s")

        self.icons = [self.prev_icon, self.play_icon, self.next_icon]
        self.image_x = [0, 0, -1]


        for i in range(0, len(self.icons)):
            self.image_y.append(MB_BUTTON_IMAGE_Y - 6)
        
        self.pressed_callback_funcs = None # set using set_callbacks()

        self.set_sensitive(True)

        focus_groups[DEFAULT_FOCUS_GROUP].append(self.widget)

        self.show_prelight_icons()
        self.stopped_prelight_icons = self.prelight_icons 
        self.icons = [self.prev_icon, self.stop_icon, self.next_icon]
        self.show_prelight_icons()
        self.playing_prelight_icons = self.prelight_icons 
        
        self.icons = [self.prev_icon, self.play_icon, self.next_icon]
        self.prelight_icons = self.stopped_prelight_icons 
        
    def set_normal_sensitive_pattern(self):
        self.set_sensitive(True)
        self.widget.queue_draw()

    def show_playing_state(self, is_playing):
        if is_playing == True:
            self.icons = [self.prev_icon, self.stop_icon, self.next_icon]
            self.prelight_icons = self.playing_prelight_icons 
        else:
            self.icons = [self.prev_icon, self.play_icon, self.next_icon]
            self.prelight_icons = self.stopped_prelight_icons
                
        self.widget.queue_draw()
        
    # ------------------------------------------------------------- mouse events
    def _press_event(self, event):
        """
        Mouse button callback
        """
        self.pressed_button = self._get_hit_code(event.x, event.y)
        if self.pressed_button >= 0 and self.pressed_button < len(self.icons):
            callback_func = self.pressed_callback_funcs[self.pressed_button] # index is set to match at editorwindow.py where callback func list is created
            callback_func()
        self.widget.queue_draw()

    def _motion_notify_event(self, x, y, state):
        """
        Mouse move callback
        """
        button_under = self._get_hit_code(x, y)
        if self.pressed_button != button_under: # pressed button is released
            self.pressed_button = NO_HIT

        if len(self.prelight_icons) > 0:
            self.prelight_index = button_under
            
        self.widget.queue_draw()

    def _release_event(self, event):
        """
        Mouse release callback
        """
        self.pressed_button = -1
        self.widget.queue_draw()

    def _leave_notify_event(self, event):
        self.prelight_index = -1
        self.widget.queue_draw()

    def _enter_notify_event(self, event):
        self.prelight_index = -1
        
    def set_callbacks(self, pressed_callback_funcs):
        self.pressed_callback_funcs = pressed_callback_funcs

    # ---------------------------------------------------------------- painting
    def _draw(self, event, cr, allocation):
        x, y, w, h = allocation
        self.allocation = allocation

        mid_x = w // 2
        buttons_width = self.button_width * len(self.icons)
        # Jul-2016 - SvdB - No changes made here, but because of the calculation of button_x the row of buttons is slightly moved right if play/pause
        # is enabled. This could be solved by setting self.button_x = 1, if wished.
        self.button_x = mid_x - (buttons_width // 2)
        self._draw_buttons(cr, w, h)
        
class GmicButtons(AbstractGlassButtons):

    def __init__(self):
        size_ind = 0
        size_adj = 1
        prefs = editorpersistance.prefs

        AbstractGlassButtons.__init__(self, MB_BUTTON_WIDTH[size_ind], MB_BUTTON_HEIGHT[size_ind], MB_BUTTON_Y, MB_BUTTONS_WIDTH[size_ind], MB_BUTTONS_HEIGHT[size_ind] - 2)

        next_icon = guiutils.get_cairo_image("next_frame_s")
        prev_icon = guiutils.get_cairo_image("prev_frame_s")
        mark_in_icon = guiutils.get_cairo_image("mark_in_s")
        mark_out_icon = guiutils.get_cairo_image("mark_out_s")
        marks_clear_icon = guiutils.get_cairo_image("marks_clear_s")
        to_mark_in_icon = guiutils.get_cairo_image("to_mark_in_s")
        to_mark_out_icon = guiutils.get_cairo_image("to_mark_out_s")

        self.icons = [prev_icon, next_icon, mark_in_icon, mark_out_icon,
                      marks_clear_icon, to_mark_in_icon, to_mark_out_icon]
        self.image_x = [8, 10, 6, 14, 5, 10, 9]

        for i in range(0, len(self.icons)):
            self.image_y.append(MB_BUTTON_IMAGE_Y)

        self.pressed_callback_funcs = [] # set using set_callbacks()

        self.set_sensitive(True)

        focus_groups[DEFAULT_FOCUS_GROUP].append(self.widget)
        
        self.show_prelight_icons()

    def set_normal_sensitive_pattern(self):
        self.set_sensitive(True)
        self.widget.queue_draw()

    # ------------------------------------------------------------- mouse events
    def _press_event(self, event):
        """
        Mouse button callback
        """
        self.pressed_button = self._get_hit_code(event.x, event.y)
        if self.pressed_button >= 0 and self.pressed_button < len(self.icons):
            callback_func = self.pressed_callback_funcs[self.pressed_button] # index is set to match at editorwindow.py where callback func list is created
            callback_func()

        self.widget.queue_draw()

    def _motion_notify_event(self, x, y, state):
        """
        Mouse move callback
        """
        button_under = self._get_hit_code(x, y)
        if self.pressed_button != button_under: # pressed button is released
            self.pressed_button = NO_HIT

        if len(self.prelight_icons) > 0:
            self.prelight_index = button_under
            
        self.widget.queue_draw()

    def _release_event(self, event):
        """
        Mouse release callback
        """
        self.pressed_button = -1
        self.widget.queue_draw()

    def _leave_notify_event(self, event):
        self.prelight_index = -1
        self.widget.queue_draw()

    def _enter_notify_event(self, event):
        self.prelight_index = -1
        
    def set_callbacks(self, pressed_callback_funcs):
        self.pressed_callback_funcs = pressed_callback_funcs

    # ---------------------------------------------------------------- painting
    def _draw(self, event, cr, allocation):
        x, y, w, h = allocation
        self.allocation = allocation

        mid_x = w / 2
        buttons_width = self.button_width * len(self.icons)
        self.button_x = mid_x - (buttons_width / 2)
        self._draw_buttons(cr, w, h)



class GlassButtonsGroup(AbstractGlassButtons):

    def __init__(self, button_width, button_height, button_y, image_x_default, image_y_default, focus_group=DEFAULT_FOCUS_GROUP):
        AbstractGlassButtons.__init__(self, button_width, button_height, button_y, button_width, button_height)
        self.released_callback_funcs = []
        self.image_x_default = image_x_default
        self.image_y_default = image_y_default
        focus_groups[focus_group].append(self.widget)

    def add_button(self, pix_buf, release_callback, image_x=None):
        if image_x == None:
            image_x = self.image_x_default
            
        self.icons.append(pix_buf)
        self.released_callback_funcs.append(release_callback)
        self.image_x.append(image_x)
        self.image_y.append(self.image_y_default)
        self.sensitive.append(True)
        self.widget.set_pref_size(len(self.icons) * self.button_width + 2, self.button_height + 2)

    def _draw(self, event, cr, allocation):
        x, y, w, h = allocation
        self.allocation = allocation
        self.button_x = 0
        self._draw_buttons(cr, w, h)

    def _press_event(self, event):
        self.pressed_button = self._get_hit_code(event.x, event.y)
        self.widget.queue_draw()

    def _motion_notify_event(self, x, y, state):
        button_under = self._get_hit_code(x, y)
        if self.pressed_button != button_under: # pressed button is released if mouse moves from over it
            if self.pressed_button > 0 and self.pressed_button < len(self.icons):
                release_func = self.released_callback_funcs[self.pressed_button]
                release_func()
            self.pressed_button = NO_HIT

        if len(self.prelight_icons) > 0:
            self.prelight_index = button_under
                
        self.widget.queue_draw()

    def _release_event(self, event):
        if self.pressed_button >= 0 and self.pressed_button < len(self.icons):
            release_func = self.released_callback_funcs[self.pressed_button]
            release_func()
        self.pressed_button = -1
        self.widget.queue_draw()

    def _leave_notify_event(self, event):
        self.prelight_index = -1
        self.widget.queue_draw()

    def _enter_notify_event(self, event):
        self.prelight_index = -1

        
class GlassButtonsToggleGroup(GlassButtonsGroup):
    def set_pressed_button(self, pressed_button_index, fire_clicked_cb=False):
        self.pressed_button = pressed_button_index
        if fire_clicked_cb == True:
            self._fire_pressed_button()
        self.widget.queue_draw()

    def _fire_pressed_button(self):
        release_func = self.released_callback_funcs[self.pressed_button]
        release_func()

    def _press_event(self, event):
        new_pressed_button = self._get_hit_code(event.x, event.y)
        if new_pressed_button == NO_HIT:
            return
        if new_pressed_button != self.pressed_button:
            self.pressed_button = new_pressed_button
            self._fire_pressed_button()
            self.widget.queue_draw()

    def _motion_notify_event(self, x, y, state):
        pass

    def _release_event(self, event):
        pass


class MarkButtons(GlassButtonsGroup):
    
    def __init__(self, callbacks):
            
        GlassButtonsGroup.__init__(self, 16, 18, 0, 0, 2)
            
        self.add_button(cairo.ImageSurface.create_from_png(respaths.IMAGE_PATH + "mark_in_xs.png"), callbacks[0])
        self.add_button(cairo.ImageSurface.create_from_png(respaths.IMAGE_PATH + "mark_out_xs.png"), callbacks[1])
        self.add_button(cairo.ImageSurface.create_from_png(respaths.IMAGE_PATH + "mark_clear_xs.png"), callbacks[2])
        self.no_decorations = True 
        
        self.show_prelight_icons()


class TooltipRunner:

    def __init__(self, glassbuttons, tooltips):
        self.glassbuttons = glassbuttons
        self.tooltips = tooltips

        self.glassbuttons.widget.set_has_tooltip(True)
        self.glassbuttons.widget.connect("query-tooltip", self.tooltip_query)
        self.glassbuttons.tooltip_runner = self

        self.last_hit_code = NO_HIT

    def tooltip_query(self, widget, x, y, keyboard_tooltip, tooltip):
        hit_code = self.glassbuttons._get_hit_code(x, y)
        if hit_code == NO_HIT:
            return False

        # This is needed to get better position for tooltips when tooltips have significantly different amount of text displayed
        if hit_code != self.last_hit_code:
            self.last_hit_code = hit_code
            self.glassbuttons.widget.trigger_tooltip_query()
            return False

        tooltip.set_markup(self.tooltips[hit_code])
        return True


def focus_group_has_focus(focus_group):
    group = focus_groups[focus_group]
    for widget in group:
        if widget.has_focus():
            return True

    return False
