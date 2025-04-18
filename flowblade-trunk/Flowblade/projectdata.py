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
Module contains objects used to capture project data.
"""

import cairo
import datetime
try:
    import mlt7 as mlt
except:
    import mlt
import hashlib
import os
import shutil

from gi.repository import GdkPixbuf

import appconsts
import editorpersistance
from editorstate import PROJECT
import mltprofiles
import patternproducer
import miscdataobjects
import respaths
import sequence
import userfolders
import utils


SAVEFILE_VERSION = 5 # This has freezed at 5 for long time, 
                     # we have used just hasattr() instead.

FALLBACK_THUMB = "fallback_thumb.png"

 
# Project events
EVENT_CREATED_BY_NEW_DIALOG = 0
EVENT_CREATED_BY_SAVING = 1
EVENT_SAVED = 2
EVENT_SAVED_AS = 3
EVENT_RENDERED = 4
EVENT_SAVED_SNAPSHOT = 5
EVENT_MEDIA_ADDED = 6
EVENT_PROFILE_CHANGED_SAVE = 7

thumbnailer = None

# Default values for project properties.
_project_properties_default_values = {appconsts.P_PROP_TLINE_SHRINK_VERTICAL:False, # Shink timeline max height if < 9 tracks
                                      appconsts.P_PROP_LAST_RENDER_SELECTIONS: None, # tuple for last render selections data
                                      appconsts.P_PROP_TRANSITION_ENCODING: None, # tuple for last rendered transition render selections data
                                      appconsts.P_PROP_DEFAULT_FADE_LENGTH: 10}  

# Flag used to decide if user should be prompt to save project on project exit.
media_files_changed_since_last_save = False

class Project:
    """
    Collection of all the data edited as a single unit.
    
    Contains collection of media files and one or more sequences
    Only one sequence is edited at a time.
    """
    def __init__(self, profile): #profile is mlt.Profile here, made using file path
        self.name = _("untitled") + appconsts.PROJECT_FILE_EXTENSION
        self.profile = profile
        self.profile_desc = profile.description()
        self.bins = []
        self.bins_graphics_default_lengths = {} # Bin.uid -> default length
        self.media_files = {} # MediaFile.id(key) -> MediaFile object.
        self.sequences = []
        self.next_media_file_id = 0 
        self.next_bin_number = 1 # This is for creating name for new bin 
        self.next_seq_number = 1 # This is for creating name for new sequence
        self.last_save_path = None
        self.events = []
        self.media_log = []
        self.media_log_groups = []
        self.proxy_data = miscdataobjects.ProjectProxyEditingData()
        self.update_media_lengths_on_load = False # old projects < 1.10 had wrong media length data which just was never used.
                                                  # 1.10 needed that data for the first time and required recreating it correctly for older projects
        self.project_properties = {} # Key value pair for misc persistent properties, dict is used that we can add these without worrying loading
        self.tracking_data = {}
        self.container_default_encoding = None # Set in coantaineractions.py by user.

        self.vault_folder = None
        self.project_data_id = None

        self.SAVEFILE_VERSION = SAVEFILE_VERSION
        
        # c_seq is the currently edited Sequence
        self.add_unnamed_sequence()
        self.c_seq = self.sequences[0]
        
        # c_bin is the currently displayed bin
        self.add_unnamed_bin()
        self.c_bin = self.bins[0]
        
        self.init_thumbnailer()

    def create_vault_folder_data(self, vault_dir):
        # This is called just once when Project is created for the first time.
        # All versions of project that are saved after this is called one time 
        # on creation time use this same data and therefore save project data in the same place.
        self.vault_folder = vault_dir
        
        md_key = str(datetime.datetime.now()) + str(os.urandom(16))
        md_str = hashlib.md5(md_key.encode('utf-8')).hexdigest()
        self.project_data_id = md_str

    def init_thumbnailer(self):
        global thumbnailer
        thumbnailer = Thumbnailer()
        thumbnailer.set_context(self.profile)

    def add_image_sequence_media_object(self, resource_path, name, length, ttl):
        media_object = self.add_media_file(resource_path)
        media_object.length = length
        media_object.name = name
        media_object.ttl = ttl

    def add_media_file(self, file_path, compound_clip_name=None, target_bin=None):
        """
        Adds media file to project if exists and file is of right type.
        """
        (directory, file_name) = os.path.split(file_path)
        (name, ext) = os.path.splitext(file_name)

        # Get media type
        media_type = sequence.get_media_type(file_path)

        # Get length and icon
        if media_type == appconsts.AUDIO:
            icon_path = respaths.IMAGE_PATH + "audio_file.png"
            length = thumbnailer.get_file_length(file_path)
            info = None
        else: # For non-audio we need write a thumbnail file and get file length while we're at it
             (icon_path, length, info) = thumbnailer.write_image(file_path)

        # Refuse files giving "fps_den" == 0, these have been seen in the wild.
        if media_type == appconsts.VIDEO and info["fps_den"] == 0.0: 
            msg = _("Video file gives value 0 for 'fps_den' property.")
            raise ProducerNotValidError(msg, file_path)
        
        # Hide file extension if enabled in user preferences
        clip_name = file_name
        if editorpersistance.prefs.hide_file_ext == True:
            clip_name = name
        
        # Media objects from compound clips need this to display to users instead of md5 hash.
        # Underlying reason, XML clip creation overwrites existing profile objects property values, https://github.com/mltframework/mlt/issues/212
        if compound_clip_name != None:
            clip_name = compound_clip_name

        # Create media file object
        media_object = MediaFile(self.next_media_file_id, file_path, 
                                 clip_name, media_type, length, icon_path, info)
        media_object.ttl = None

        self._add_media_object(media_object, target_bin)
        
        return media_object

    def add_title_item(self, name, file_path, title_data, target_bin):
        (directory, file_name) = os.path.split(file_path)
        (fn, ext) = os.path.splitext(file_name)

        # Get media type
        media_type = appconsts.IMAGE

        # Get length and icon
        (icon_path, length, info) = thumbnailer.write_image(file_path)
        
        clip_name = name

        # Create media file object
        media_object = MediaFile(self.next_media_file_id, file_path, 
                                 clip_name, media_type, length, icon_path, info)
        media_object.ttl = None
        media_object.titler_data = title_data

        self._add_media_object(media_object, target_bin)

    def add_pattern_producer_media_object(self, media_object):
        self._add_media_object(media_object)
        
    def add_container_clip_media_object(self, media_object):
        self._add_media_object(media_object)

    def add_sequence_link_media_object(self, media_object, link_seq_uid):
        media_object.link_seq_data = link_seq_uid
        self._add_media_object(media_object)
        
    def _add_media_object(self, media_object, target_bin=None):
        """
        Adds media file or color clip to project data structures.
        """
        global media_files_changed_since_last_save
        media_files_changed_since_last_save = True
        
        self.media_files[media_object.id] = media_object
        self.next_media_file_id += 1

        # Add to bin
        if target_bin == None:
            self.c_bin.file_ids.append(media_object.id)
        else:
            target_bin.file_ids.append(media_object.id)

    def media_file_exists(self, file_path):
        for key, media_file in list(self.media_files.items()):
            if media_file.type == appconsts.PATTERN_PRODUCER:
                continue
            if media_file.container_data != None:
                continue
            if file_path == media_file.path:
                return True

        return False

    def get_bin_for_media_file_id(self, media_file_id):
        for bin in self.bins:
            for file_id in bin.file_ids:
                if file_id == media_file_id:
                    return bin
        return None
        
    def get_media_file_for_path(self, file_path):
        for key, media_file in list(self.media_files.items()):
            if media_file.type == appconsts.PATTERN_PRODUCER:
                continue
            if file_path == media_file.path:
                return media_file
        return None

    def get_media_file_for_second_path(self, file_path):
        for key, media_file in list(self.media_files.items()):
            if media_file.type == appconsts.PATTERN_PRODUCER:
                continue            
            if file_path == media_file.second_file_path:
                return media_file
        return None

    def get_media_file_for_container_data(self, container_data):
        for key, media_file in list(self.media_files.items()):
            if media_file.type == appconsts.PATTERN_PRODUCER:
                continue
            if media_file.container_data == None:
                continue
            if media_file.container_data.program == container_data.program and \
                media_file.container_data.unrendered_media == container_data.unrendered_media:
                return media_file
        return None
        
    def delete_media_file_from_current_bin(self, media_file):
        global media_files_changed_since_last_save
        media_files_changed_since_last_save = True

        self.c_bin.file_ids.pop(media_file.id)

    def get_unused_media(self):
        # Create path -> media item dict
        path_to_media_object = {}
        for key, media_item in list(self.media_files.items()):
            if hasattr(media_item, "path") and media_item.path != "" and media_item.path != None:
                path_to_media_object[media_item.path] = media_item
        
        # Remove all items from created dict that have a clip with same path on any of the sequences
        for seq in self.sequences:
            for track in seq.tracks:
                for clip in track.clips:
                    try:
                        path_to_media_object.pop(clip.path)
                    except:
                        pass
    
        # Create a list of unused media objects
        unused = []
        for path, media_item in list(path_to_media_object.items()):
            unused.append(media_item)
        return unused
    
    def get_current_proxy_paths(self):
        paths_dict = {}
        for idkey, media_file in list(self.media_files.items()):
            try:
                if media_file.is_proxy_file:
                    paths_dict[media_file.path] = media_file
            except AttributeError: # Pattern producers or old media files do not have these, add values
                self.has_proxy_file = False
                self.is_proxy_file = False
                self.second_file_path = None

        return paths_dict

    def add_unnamed_bin(self):
        """
        Adds bin with default name.
        """
        name = _("bin_") + str(self.next_bin_number)
        self.bins.append(Bin(name))
        self.next_bin_number += 1
    
    def add_unnamed_sequence(self):
        """
        Adds sequence with default name
        """
        name = _("sequence_") + str(self.next_seq_number)
        self.add_named_sequence(name)

    def get_sequence_for_uid(self, seq_uid):
        for seq in self.sequences:
            if seq.uid == seq_uid:
                return seq
        return None

    def get_current_bin_graphics_default_length(self):
        try:
            return self.bins_graphics_default_lengths[self.c_bin.uid]
        except:
            return editorpersistance.prefs.default_grfx_length

    def set_current_bin_graphics_default_length(self, default_length):
        self.bins_graphics_default_lengths[self.c_bin.uid] = default_length
            
    def add_named_sequence(self, name):
        seq = sequence.Sequence(self.profile, appconsts.COMPOSITING_MODE_STANDARD_FULL_TRACK)
        seq.create_default_tracks()
        seq.name = name
        self.sequences.append(seq)
        self.next_seq_number += 1

    def get_filtered_media_log_events(self, group_index, incl_starred, incl_not_starred, sorting_order):
        filtered_events = []
        if group_index < 0:
            view_items = self.media_log
        else:
            name, items = self.media_log_groups[group_index]
            view_items = items
        for media_log_event in view_items:
            if self._media_log_included_by_starred(media_log_event.starred, incl_starred, incl_not_starred):
                filtered_events.append(media_log_event)
        
        if sorting_order == appconsts.NAME_SORT:
            filtered_events = sorted(filtered_events, key=lambda mevent: mevent.name)
        elif sorting_order == appconsts.COMMENT_SORT:
            filtered_events = sorted(filtered_events, key=lambda mevent: mevent.comment)

        return filtered_events

    def _media_log_included_by_starred(self, starred, incl_starred, incl_not_starred):
        if starred == True and incl_starred == True:
            return True
        if starred == False and incl_not_starred == True:
            return True
        return False

    def delete_media_log_events(self, items):
        for i in items:
            self.media_log.remove(i)

    def remove_from_group(self, group_index, items):
        if group_index < 0: # -1 is used as "All" group index in medialog.py, but it isn't group, it is contents of self.media_log
            return
        name, group_items = self.media_log_groups[group_index]
        for i in items:
            group_items.remove(i)

    def add_to_group(self, group_index, items):
        if group_index < 0: # -1 is used as "All" group index in medialog.py, but it isn't group, it is contents of self.media_log
            return
        name, group_items = self.media_log_groups[group_index]
        for i in items:
            try:
                group_items.remove(i) # single ref to item in list allowed
            except:
                pass
            group_items.append(i)

    def add_media_log_group(self, name, items):
        self.media_log_groups.append((name, items))

    def exit_clip_renderer_process(self):
        pass

    def get_last_render_folder(self):
        last_render_event = None
        for pe in self.events:
            if pe.event_type == EVENT_RENDERED:
                last_render_event = pe
        if last_render_event == None:
            return None

        return os.path.dirname(last_render_event.data)

    def is_first_video_load(self):
        for uid, media_file in self.media_files.items():
            if media_file.type == appconsts.VIDEO:
                return False
        
        return True

    def get_project_property(self, property_name):
        try:
            return self.project_properties[property_name]
        except:
            try:
                return _project_properties_default_values[property_name]
            except:
                return None # No default values for all properties exist, action value decided at callsite in that case

    def set_project_property(self, property_name, value):
        self.project_properties[property_name] = value

    def add_tracking_data(self, data_label, data_file_path):
        data_uid = utils.get_uid_str()
        
        # Get unique data label
        add_number = 1
        final_label = data_label
        while self._tracking_data_label_exists(final_label):
            final_label = data_label + "-" + str(add_number)
            add_number += 1
        
        self.tracking_data[data_uid] = (final_label, data_file_path)
        return final_label

    def delete_tracking_data(self, tracking_data_id):
        final_label, data_file_path = self.tracking_data[tracking_data_id]
        try:
            os.remove(data_file_path)
        except:
            print("ProjectData.delete_tracking_data(): trying to delete non-existing data") 
        del self.tracking_data[tracking_data_id]

    def _tracking_data_label_exists(self, data_label):
        for item in self.tracking_data.items():
            label, data_path = item
            if data_label == label:
                return True
        return False

class MediaFile:
    """
    Media file that can added to and edited in Sequence.
    """
    def __init__(self, id, file_path, name, media_type, length, icon_path, info):
        self.id = id
        self.path = file_path
        self.name = name
        self.type = media_type
        self.length = length
        self.icon_path = icon_path
        self.icon = None
        self.create_icon()

        self.mark_in = -1
        self.mark_out = -1

        self.has_proxy_file = False
        self.is_proxy_file = False
        self.second_file_path = None # to proxy when original, to original when proxy
        
        self.current_frame = 0

        self.container_data = None
        self.titler_data = None
        self.link_seq_data = None
        
        self.info = info
        self.rating = appconsts.MEDIA_FILE_UNRATED
        
        # Set default length for graphics files
        (f_name, ext) = os.path.splitext(self.name)
        if utils.file_extension_is_graphics_file(ext) and self.type != appconsts.IMAGE_SEQUENCE:
            in_fr, out_fr, l = editorpersistance.get_graphics_default_in_out_length()
            self.mark_in = in_fr
            self.mark_out = out_fr
            self.length = l
 
    def create_icon(self):
        try:
            self.icon = self._create_image_surface(self.icon_path)
        except:
            print("failed to make icon from:", self.icon_path)
            self.icon_path = respaths.IMAGE_PATH + FALLBACK_THUMB
            self.icon = self._create_image_surface(self.icon_path)

    def _create_image_surface(self, path):
        icon = cairo.ImageSurface.create_from_png(self.icon_path)
        scaled_icon = cairo.ImageSurface(cairo.FORMAT_ARGB32, appconsts.THUMB_WIDTH, appconsts.THUMB_HEIGHT)
        cr = cairo.Context(scaled_icon)
        cr.scale(float(appconsts.THUMB_WIDTH) / float(icon.get_width()), float(appconsts.THUMB_HEIGHT) / float(icon.get_height()))
        cr.set_source_surface(icon, 0, 0)
        cr.paint()
        
        return scaled_icon

    def create_proxy_path(self, proxy_width, proxy_height, file_extesion):
        if self.type == appconsts.IMAGE_SEQUENCE:
            return self._create_img_seg_proxy_path(proxy_width, proxy_height)
        
        proxy_md_key = self.path + str(proxy_width) + str(proxy_height)
        if hasattr(self, "use_unique_proxy"): # This may have been added in proxyediting.py to prevent interfering with existing projects
            proxy_md_key = proxy_md_key + str(os.urandom(16))
        md_str = hashlib.md5(proxy_md_key.encode('utf-8')).hexdigest()
        return str(userfolders.get_proxies_dir() + md_str + "." + file_extesion) # str() because we get unicode here

    def _create_img_seg_proxy_path(self,  proxy_width, proxy_height):
        folder, file_name = os.path.split(self.path)
        proxy_md_key = self.path + str(proxy_width) + str(proxy_height)
        if hasattr(self, "use_unique_proxy"): # This may have been added in proxyediting.py to prevent interfering with existing projects
            proxy_md_key = proxy_md_key + str(os.urandom(16))
        md_str = hashlib.md5(proxy_md_key.encode('utf-8')).hexdigest()
        return str(userfolders.get_proxies_dir() + md_str + "/" + file_name)

    def add_proxy_file(self, proxy_path):
        self.has_proxy_file = True
        self.second_file_path = proxy_path

    def add_existing_proxy_file(self, proxy_width, proxy_height, file_extesion):
        proxy_path = self.create_proxy_path(proxy_width, proxy_height, file_extesion)
        self.add_proxy_file(proxy_path)

    def set_as_proxy_media_file(self):
        self.path, self.second_file_path = self.second_file_path, self.path
        self.is_proxy_file = True

    def set_as_original_media_file(self):
        self.path, self.second_file_path = self.second_file_path, self.path
        self.is_proxy_file = False

    def matches_project_profile(self):
        if (not hasattr(self, "info")): # to make really sure that old projects don't crash,
            return True                            # but probably is not needed as attr is added at load
        if self.info == None:
            return True
        
        is_match = True # this is true for audio and graphics and image sequences and is only 
                        # set false for video that does not match profile
                        
        if self.type == appconsts.VIDEO:
            best_media_profile_index = mltprofiles.get_closest_matching_profile_index(self.info)
            project_profile_index = mltprofiles.get_index_for_name(PROJECT().profile.description())
            if best_media_profile_index != project_profile_index:
                is_match = False
        
        return is_match
        

class BinColorClip:
    # DECPRECATED, this is replaced by patternproducer.BinColorClip.
    # This is kept for project file backwards compatibility,
    # unpickle fails for color clips if this isn't here.
    # kill 2016-ish
    def __init__(self, id, name, gdk_color_str):
        self.id = id
        self.name = name
        self.gdk_color_str = gdk_color_str
        self.length = 15000
        self.type = appconsts.PATTERN_PRODUCER
        self.icon = None
        self.create_icon()
        self.patter_producer_type = patternproducer.COLOR_CLIP

        self.mark_in = -1
        self.mark_out = -1

    def create_icon(self):
        icon = GdkPixbuf.Pixbuf(GdkPixbuf.Colorspace.RGB, False, 8, appconsts.THUMB_WIDTH, appconsts.THUMB_HEIGHT)
        pixel = utils.gdk_color_str_to_int(self.gdk_color_str)
        icon.fill(pixel)
        self.icon = icon


class Bin:
    """
    Group of media files
    """
    def __init__(self, name="name"):
        self.uid = hashlib.md5(str(os.urandom(32)).encode('utf-8')).hexdigest()
        self.name = name # Displayed name
        self.file_ids = [] # List of media files ids in the bin.
                           # Ids are increasing integers given in 
                           # Project.add_media_file(...)


class ProducerNotValidError(Exception):
    def __init__(self, value, file_path):
        self.value = value
        self.file_path = file_path

    def __str__(self):
        return repr(self.value)


class Thumbnailer:
    def __init__(self):
        self.profile = None

    def set_context(self, profile):
        self.profile = profile
    
    def write_image(self, file_path):
        """
        Writes thumbnail image from file producer
        """
        # Get data
        md_str = hashlib.md5(file_path.encode('utf-8')).hexdigest()
        thumbnail_path = userfolders.get_thumbnail_dir() + md_str + ".png"
        render_image_path = userfolders.get_cache_dir() + "thumbnail%03d.png"

        # Create consumer
        consumer = mlt.Consumer(self.profile, "avformat", 
                                     render_image_path)
        consumer.set("real_time", 0)
        consumer.set("vcodec", "png")

        # Create one frame producer
        producer = mlt.Producer(self.profile, str(file_path))
        if producer.is_valid() == False:
            msg = _("MLT reports that file is not a valid media producer.")
            raise ProducerNotValidError(msg, file_path)
            
        info = utils.get_file_producer_info(producer)

        length = producer.get_length()
        frame = length // 2
        producer = producer.cut(frame, frame)

        # Connect and write image
        consumer.connect(producer)
        consumer.run()
        
        # consumer.run() blocks until done so the thubnailfile is now ready to be copied.
        shutil.copyfile(userfolders.get_cache_dir() + "thumbnail001.png", thumbnail_path)
        
        return (thumbnail_path, length, info)

    def get_file_length(self, file_path):
        # This is used for audio files which don't need a thumbnail written
        # but do need file length known

        producer = mlt.Producer(self.profile, str(file_path))
        if producer.get("seekable") == "0":
            msg = _("Audio file not seekable, cannot be edited.\n\n")
            raise ProducerNotValidError(msg, file_path)
        return producer.get_length()


# ----------------------------------- project and media log events
class ProjectEvent:
    def __init__(self, event_type, data):
        self.event_type = event_type
        self.timestamp = datetime.datetime.now()
        self.data = data

    def get_date_str(self):
        date_str = self.timestamp.strftime('%Y %b %d, %H:%M')
        date_str = date_str.lstrip('0')
        return date_str

    def get_desc_and_path(self):
        if self.event_type == EVENT_CREATED_BY_NEW_DIALOG:
            return (_("Created using dialog"), None)
        elif self.event_type == EVENT_CREATED_BY_SAVING:
            return (_("Created using Save As... "), self.data)
        elif self.event_type == EVENT_SAVED:
            return (_("Saved "), self.data)
        elif self.event_type == EVENT_SAVED_AS:
            name, path = self.data
            return (_("Saved as ") + name, path)
        elif self.event_type == EVENT_RENDERED:
            return (_("Rendered "), self.data)
        elif self.event_type == EVENT_SAVED_SNAPSHOT:
            return (_("Saved backup snapshot"), self.data)
        elif self.event_type == EVENT_MEDIA_ADDED:
            return (_("Media load"), self.data)
        elif self.event_type == EVENT_PROFILE_CHANGED_SAVE:
            return (_("Saved with changed profile"), self.data)
        else:
            return ("Unknown project event, bug or data corruption", None)



# ------------------------------- MODULE FUNCTIONS
def get_default_project():
    """
    Creates the project displayed at start up.
    """
    profile = mltprofiles.get_default_profile()
    project = Project(profile)
    return project


    
    
    
