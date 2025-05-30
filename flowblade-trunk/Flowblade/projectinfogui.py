"""
    Flowblade Movie Editor is a nonlinear video editor.
    Copyright 2013 Janne Liljeblad.

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


from gi.repository import Gtk
from gi.repository import GObject
from gi.repository import Pango

import dialogutils
import editorstate
from editorstate import PROJECT
import guicomponents
import guiutils
import utils

widgets = utils.EmptyClass()


def get_project_info_panel():
    project_name_label = Gtk.Label(label=PROJECT().name)
    name_row = guiutils.get_left_justified_box([project_name_label])
    name_vbox = Gtk.VBox()
    name_vbox.pack_start(name_row, False, False, 0)
    name_vbox.pack_start(Gtk.Label(), True, True, 0)
    name_panel = guiutils.get_named_frame(_("Name"), name_vbox, 4)
    
    profile = PROJECT().profile
    desc_label = Gtk.Label(label=profile.description())
    info_box = guicomponents.get_profile_info_small_box(profile)
    vbox = Gtk.VBox()
    vbox.pack_start(guiutils.get_left_justified_box([desc_label]), False, True, 0)
    vbox.pack_start(info_box, False, True, 0)
    profile_panel = guiutils.get_named_frame(_("Profile"), vbox, 4)

    project_info_hbox = Gtk.HBox()
    project_info_hbox.pack_start(name_panel, False, True, 0)
    project_info_hbox.pack_start(guiutils.pad_label(24, 24), False, True, 0)
    project_info_hbox.pack_start(profile_panel, False, True, 0)
    project_info_hbox.pack_start(Gtk.Label(), True, True, 0)
    
    widgets.project_name_label = project_name_label
    widgets.monitor_desc_label = desc_label
    widgets.info_box = info_box

    return project_info_hbox

def get_top_level_project_info_panel():
    
    # This all is now just a text in topbar with manu bar and monitors rc info widget.
    profile = PROJECT().profile
    desc_label = Gtk.Label(label=profile.description())
    if editorstate.screen_size_small_height() == True:
        font_desc = "sans bold 8"
    else:
        font_desc = "sans bold 9"
    desc_label.modify_font(Pango.FontDescription(font_desc))
    desc_label.set_sensitive(False)
    desc_row = guiutils.get_left_justified_box([desc_label])
    desc_row.set_margin_start(4)

    project_info_vbox = Gtk.HBox()
    #dash_label = Gtk.Label()
    #dash_label.set_text("-")
    #dash_label.modify_font(Pango.FontDescription(font_desc))
    #dash_label.set_sensitive(False)
    #project_info_vbox.pack_start(dash_label, False, False, 0)
    project_info_vbox.pack_start(desc_row, False, False, 0)
    guiutils.set_margins(project_info_vbox, 2,0,4,0)

    project_info_vbox.set_tooltip_text(guicomponents.get_full_profile_info_text(profile))

    widgets.monitor_desc_label = desc_label

    # We are leaving this to keep updates working for now because smaller window sizes use this reference 'widgets.info_box' still.
    info_box = guicomponents.get_profile_info_reduced_small_box(profile)
    widgets.info_box = info_box
 
    return project_info_vbox
    
def update_project_info():
    profile = PROJECT().profile
    widgets.monitor_desc_label.set_text(profile.description())
    profile_info_text = guicomponents.get_profile_reduced_info_text(profile)
    widgets.info_box.get_children()[0].set_text(profile_info_text)


class ProjectEventListView(Gtk.VBox):

    def __init__(self):
        GObject.GObject.__init__(self)

       # Datamodel: text, text, text
        self.storemodel = Gtk.ListStore(str, str, str)

        # Scroll container
        self.scroll = Gtk.ScrolledWindow()
        self.scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        # View
        self.treeview = Gtk.TreeView(model=self.storemodel)
        self.treeview.set_property("rules_hint", True)
        self.treeview.set_headers_visible(True)
        tree_sel = self.treeview.get_selection()
        tree_sel.set_mode(Gtk.SelectionMode.SINGLE)

        # Column views
        self.text_col_1 = Gtk.TreeViewColumn("text1")
        self.text_col_1.set_title(_("Date"))
        self.text_col_2 = Gtk.TreeViewColumn("text2")
        self.text_col_2.set_title(_("Event"))
        self.text_col_3 = Gtk.TreeViewColumn("text3")
        self.text_col_3.set_title(_("Data"))

        # Cell renderers
        self.text_rend_1 = Gtk.CellRendererText()
        self.text_rend_1.set_property("ellipsize", Pango.EllipsizeMode.END)

        self.text_rend_2 = Gtk.CellRendererText()
        self.text_rend_2.set_property("yalign", 0.0)

        self.text_rend_3 = Gtk.CellRendererText()
        self.text_rend_3.set_property("yalign", 0.0)

        # Build column views
        self.text_col_1.set_expand(True)
        self.text_col_1.set_spacing(5)
        self.text_col_1.set_sizing(Gtk.TreeViewColumnSizing.GROW_ONLY)
        self.text_col_1.set_min_width(150)
        self.text_col_1.pack_start(self.text_rend_1, True)
        self.text_col_1.add_attribute(self.text_rend_1, "text", 0)

        self.text_col_2.set_expand(True)
        self.text_col_2.pack_start(self.text_rend_2, True)
        self.text_col_2.add_attribute(self.text_rend_2, "text", 1)

        self.text_col_3.set_expand(True)
        self.text_col_3.pack_start(self.text_rend_3, True)
        self.text_col_3.add_attribute(self.text_rend_3, "text", 2)
        
        # Add column views to view
        self.treeview.append_column(self.text_col_1)
        self.treeview.append_column(self.text_col_2)
        self.treeview.append_column(self.text_col_3)

        # Build widget graph and display
        self.scroll.add(self.treeview)
        self.pack_start(self.scroll, True, True, 0)
        self.scroll.show_all()

    def fill_data_model(self):
        self.storemodel.clear()
        for e in PROJECT().events:
            t = e.get_date_str()
            desc, path = e.get_desc_and_path()
            row_data = [t, desc, path]
            self.storemodel.append(row_data)
        
        self.scroll.queue_draw()
    
