"""

    KeepNote    
    ListView

"""

#
#  KeepNote
#  Copyright (c) 2008-2011 Matt Rasmussen
#  Author: Matt Rasmussen <rasmus@mit.edu>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301, USA.
#

import gettext

# pygtk imports
import pygtk
pygtk.require('2.0')
import gtk, gobject, pango
from gtk import gdk

from keepnote.timestamp import get_str_timestamp
from keepnote.gui import basetreeview
from keepnote.gui import \
     get_resource, \
     get_resource_image, \
     get_resource_pixbuf
from keepnote.gui.icons import get_node_icon
from keepnote.gui import treemodel
from keepnote import notebook
from keepnote.notebook import NoteBookError
import keepnote

_ = keepnote.translate


DEFAULT_ATTR_COL_WIDTH = 150
DEFAULT_TITLE_COL_WIDTH = 250


class KeepNoteListView (basetreeview.KeepNoteBaseTreeView):
    
    def __init__(self):
        basetreeview.KeepNoteBaseTreeView.__init__(self)
        self._sel_nodes = None
        self._date_formats = {}
        self._attr_col_widths = {"title": DEFAULT_TITLE_COL_WIDTH}
        self._columns = ["title", "created_time", "modified_time"]

        # configurable callback for setting window status
        self.on_status = None        
        
        # selection config
        self.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
        
        # init view
        self.connect("key-release-event", self.on_key_released)
        self.connect("button-press-event", self.on_button_press)
        self.connect("row-expanded", self._on_listview_row_expanded)
        self.connect("row-collapsed", self._on_listview_row_collapsed)
        
        self.set_rules_hint(True)
        self.set_fixed_height_mode(True)
        self.set_sensitive(False)        

        # init model
        self.set_model(gtk.TreeModelSort(treemodel.KeepNoteTreeModel()))
        
        self.setup_columns()
    
    
    def load_preferences(self, app_pref, first_open=False):
        """Load application preferences"""
        self.set_date_formats(app_pref.get("timestamp_formats"))
        self.set_rules_hint(
            app_pref.get("look_and_feel", "listview_rules",
                         default=True))


    def save_preferences(self, app_pref):
        """Save application preferences"""
        pass                


    def set_notebook(self, notebook):
        """Set the notebook for listview"""

        #if self._notebook is not None:
        #    # save notebook prefs
        #    self.save()

        basetreeview.KeepNoteBaseTreeView.set_notebook(self, notebook)
        
        if self.rich_model is not None:
            self.rich_model.set_root_nodes([])

        if notebook:
            # load notebook prefs
            self.set_sensitive(True)
            
            # load attr column widths
            for attr, width in notebook.get_attr("column_widths", {}).items():
                self._attr_col_widths[attr] = width


        else:
            self.set_sensitive(False)

        self.setup_columns()


    def save(self):
        """Save notebook preferences"""
        
        # save attr column widths
        widths = self._notebook.get_attr("column_widths", {})
        for i, attr in enumerate(self._columns):
            widths[attr] = self.get_column(i).get_width()
        self._notebook.set_attr("column_widths", widths)
        self._notebook.mark_modified()


    #==================================
    # model and view setup


    def set_model(self, model):
        basetreeview.KeepNoteBaseTreeView.set_model(self, model)
        self.model.connect("sort-column-changed", self._sort_column_changed)



    def clear_columns(self):
        for col in reversed(self.get_columns()):
            self.remove_column(col)


    def setup_columns(self):

        if self._notebook is None:
            self.clear_columns()
            return
        
        # TODO: eventually columns may change when ever master node changes
        self._columns = self._notebook.attr_tables.get("default").attrs
        
        
        # add columns        
        for attr in self._columns:
            col = self._add_column(attr)
            if attr == "title":
                self.title_column = col

        # add model columns
        self._add_model_column("order")
        
        # NOTE: must create a new TreeModelSort whenever we add new columns
        # to the rich_model that could be used in sorting
        # Perhaps something is being cached
        self.set_model(gtk.TreeModelSort(self.rich_model))
        
        
        # config columns view
        self.set_expander_column(self.get_column(0))

        # TODO: load correct sorting right away
        # set default sorting
        # remember sort per node
        self.model.set_sort_column_id(
            self.rich_model.get_column_by_name("order").pos,
            gtk.SORT_ASCENDING)
        self.set_reorder(basetreeview.REORDER_ALL)
        

    def _add_column(self, attr, cell_attr=None):
        
        # get attribute definition from notebook
        attr_def = self._notebook.attr_defs.get(attr)

        # get datatype
        if attr_def is not None:
            datatype = attr_def.datatype
            col_title = attr_def.name
        else:
            datatype = "string"
            col_title = attr

        # get/make model column
        self._add_model_column(attr)

        # create column view
        column = gtk.TreeViewColumn()
        column.set_property("sizing", gtk.TREE_VIEW_COLUMN_FIXED)
        column.set_property("resizable", True)
        column.set_min_width(10)
        column.set_fixed_width(
            self._attr_col_widths.get(attr, DEFAULT_ATTR_COL_WIDTH))
        column.set_title(col_title)

        # define column sorting
        attr_sort = attr + "_sort"
        col =  self.rich_model.get_column_by_name(attr_sort)
        if col:
            column.set_sort_column_id(col.pos)

        # add cell renders
        if attr == "title":
            self._add_title_render(column, attr)
        else:
            self._add_text_render(column, attr)


        self.append_column(column)

        return column


    def _add_title_render(self, column, attr):

        attr_icon = "icon"
        attr_icon_open = "icon_open"

        # make sure icon attributes are in model
        self._add_model_column(attr_icon)
        self._add_model_column(attr_icon_open)

        # add renders
        cell_icon = self._add_pixbuf_render(column, attr_icon, attr_icon_open)
        title_text = self._add_text_render(column, attr, editable=True)

        # record reference to title_text renderer
        self.title_text = title_text

        return cell_icon, title_text


    def _add_text_render(self, column, attr, editable=False):

        # cell renderer text
        cell_text = gtk.CellRendererText()
        cell_text.set_fixed_height_from_font(1)
        column.pack_start(cell_text, True)
        column.add_attribute(cell_text, 'text', 
                             self.rich_model.get_column_by_name(attr).pos)
        
        # set edit callbacks
        if editable:
            cell_text.connect("edited", lambda r,p,t: self.on_edit_attr(
                    r, p, attr, t, validate=lambda t: t != ""))
            cell_text.connect("editing-started", self.on_editing_started)
            cell_text.connect("editing-canceled", self.on_editing_canceled)
            cell_text.set_property("editable", True)

        return cell_text


    def _add_pixbuf_render(self, column, attr, attr_open=None):
        
        cell = gtk.CellRendererPixbuf()
        column.pack_start(cell, False)
        column.add_attribute(cell, 'pixbuf',
            self.rich_model.get_column_by_name(attr).pos)
        if attr_open:
            column.add_attribute(cell, 'pixbuf-expander-open',
                self.rich_model.get_column_by_name(attr_open).pos)

        return cell
    
    
    def _add_model_column(self, attr, add_sort=True):
 
        # get attribute definition from notebook
        attr_def = self._notebook.attr_defs.get(attr)

        # get datatype
        if attr_def is not None:
            datatype = attr_def.datatype
            default = attr_def.default
        else:
            datatype = "string"
            default = ""

        # value fetching
        get = lambda node: mapfunc(node.get_attr(attr, default))
        get_sort = lambda node: mapfunc_sort(node.get_attr(attr, default))

        # get coltype
        mapfunc = lambda x: x
        mapfunc_sort = lambda x: x
        if datatype == "string":
            coltype = str
            coltype_sort = str
            mapfunc_sort = lambda x: x.lower()
        elif datatype == "integer":
            coltype = int
            coltype_sort = int
        elif datatype == "float":
            coltype = float
            coltype_sort = float
        elif datatype == "timestamp":
            mapfunc = self.format_timestamp
            coltype = str
            coltype_sort = int
        else:
            coltype = str
            coltype_sort = str
        
        
        # builtin column types
        if attr == "icon":
            coltype = gdk.Pixbuf
            coltype_sort = None
            get = lambda node: get_node_icon(node, False,
                                             node in self.rich_model.fades)
        elif attr == "icon_open":
            coltype = gdk.Pixbuf
            coltype_sort = None
            get = lambda node: get_node_icon(node, True,
                                             node in self.rich_model.fades)


        # get/make model column
        col = self.rich_model.get_column_by_name(attr)
        if col is None:
            col = treemodel.TreeModelColumn(attr, coltype, attr=attr, get=get)
            self.rich_model.append_column(col)
        
        # define column sorting
        if coltype_sort is not None:
            attr_sort = attr + "_sort"
            col = self.rich_model.get_column_by_name(attr_sort)
            if col is None:
                col = treemodel.TreeModelColumn(
                    attr_sort, coltype_sort, attr=attr, get=get_sort)
                self.rich_model.append_column(col)


    def set_date_formats(self, formats):
        """Sets the date formats of the treemodel"""
        self._date_formats = formats


    def format_timestamp(self, timestamp):
        return (get_str_timestamp(timestamp, formats=self._date_formats)
                if timestamp is not None else u"")


    #=============================================
    # gui callbacks    


    def is_node_expanded(self, node):
        return node.get_attr("expanded2", False)

    def set_node_expanded(self, node, expand):

        # don't save the expand state of the master node
        if len(treemodel.get_path_from_node(
               self.model, node,
               self.rich_model.get_node_column_pos())) > 1:
            node.set_attr("expanded2", expand)
            

    def _sort_column_changed(self, sortmodel):
        self._update_reorder()
        

    def _update_reorder(self):
        col_id, sort_dir = self.model.get_sort_column_id()

        if col_id is None or col_id < 0:
            col = None
        else:
            col = self.rich_model.get_column(col_id)
        
        if col is None: #  or col.attr == "order"
            self.model.set_sort_column_id(
                self.rich_model.get_column_by_name("order").pos,
                gtk.SORT_ASCENDING)
            self.set_reorder(basetreeview.REORDER_ALL)
        else:
            self.set_reorder(basetreeview.REORDER_FOLDER)        

    
    def on_key_released(self, widget, event):
        """Callback for key release events"""

        # no special processing while editing nodes
        if self.editing_path:
            return

        if event.keyval == gtk.keysyms.Delete:
            # capture node deletes
            self.stop_emission("key-release-event")
            self.emit("delete-node", self.get_selected_nodes())
            
        elif event.keyval == gtk.keysyms.BackSpace and \
             event.state & gdk.CONTROL_MASK:
            # capture goto parent node
            self.stop_emission("key-release-event")
            self.emit("goto-parent-node")


        elif event.keyval == gtk.keysyms.Return and \
             event.state & gdk.CONTROL_MASK:
            # capture goto node
            self.stop_emission("key-release-event")
            self.emit("activate-node", None)
            


    def on_button_press(self, widget, event):
        if event.button == 3:            
            # popup menu
            return self.popup_menu(event.x, event.y, event.button, event.time)
            

        if event.button == 1 and event.type == gtk.gdk._2BUTTON_PRESS:
            model, paths = self.get_selection().get_selected_rows()
            # double click --> goto node
            if len(paths) > 0:
                nodes = [self.model.get_value(self.model.get_iter(x),
                                              self.rich_model.get_node_column_pos())
                         for x in paths]

                # NOTE: can only view one node
                self.emit("activate-node", nodes[0])
    

    def is_view_tree(self):

        # TODO: document this more
        return self.get_master_node() is not None
    
    #====================================================
    # actions
    
    def view_nodes(self, nodes, nested=True):
        # TODO: learn how to deactivate expensive sorting
        #self.model.set_default_sort_func(None)
        #self.model.set_sort_column_id(-1, gtk.SORT_ASCENDING)
        
        # save sorting if a single node was selected
        if self._sel_nodes is not None and len(self._sel_nodes) == 1:
            self.save_sorting(self._sel_nodes[0])
            
        if len(nodes) > 1:
            nested = False
        
        self._sel_nodes = nodes
        self.rich_model.set_nested(nested)

        # set master node
        self.set_master_node(None)
        
        # populate model
        roots = nodes
        self.rich_model.set_root_nodes(roots)

        # load sorting if single node is selected
        if len(nodes) == 1:
            self.load_sorting(nodes[0], self.model)
        
        # expand rows
        for node in roots:
            self.expand_to_path(treemodel.get_path_from_node(
                self.model, node, self.rich_model.get_node_column_pos()))

        # disable if no roots
        if len(roots) == 0:
            self.set_sensitive(False)
        else:
            self.set_sensitive(True)

        # update status
        self.display_page_count()

        self.emit("select-nodes", [])



    def get_root_nodes(self):
        """Returns the root nodes displayed in listview"""
        if self.rich_model:
            return self.rich_model.get_root_nodes()
        else:
            return []
    

    def append_node(self, node):

        # do not allow appending of nodes unless we are masterless
        if self.get_master_node() is not None:
            return

        self.rich_model.append(node)
        
        if node.get_attr("expanded2", False):
            self.expand_to_path(treemodel.get_path_from_node(
                self.model, node, self.rich_model.get_node_column_pos()))

        self.set_sensitive(True)        

        # update status
        #self.display_page_count()


    def display_page_count(self, npages=None):

        if npages is None:
            #npages = len(self.get_root_nodes())
            npages = self.count_pages(self.get_root_nodes())

        if npages != 1:
            self.set_status(_("%d pages") % npages, "stats")
        else:
            self.set_status(_("1 page"), "stats")


    def count_pages(self, roots):

        # TODO: is there a way to make this faster?
        
        def walk(node):
            npages = 1
            if (self.rich_model.get_nested() and 
                (node.get_attr("expanded2", False))):
                for child in node.get_children():
                    npages += walk(child)
            return npages

        return sum(walk(child) for node in roots
                   for child in node.get_children())
        
    
    def edit_node(self, page):
        path = treemodel.get_path_from_node(
            self.model, page, self.rich_model.get_node_column_pos())
        if path is None:
            # view page first if not in view
            self.emit("goto-node", page)
            path = treemodel.get_path_from_node(
                self.model, page, self.rich_model.get_node_column_pos())
            assert path is not None
        self.set_cursor_on_cell(path, self.title_column, self.title_text, True)
        path, col = self.get_cursor()
        self.scroll_to_cell(path)
        

    #def cancel_editing(self):
    #    # TODO: add this
    #    pass
    #    #self.cell_text.stop_editing(True)

    
    def save_sorting(self, node):
        """Save sorting information into node"""

        info_sort, sort_dir = self.model.get_sort_column_id()

        if sort_dir == gtk.SORT_ASCENDING:
            sort_dir = 1
        else:
            sort_dir = 0

        if info_sort is None or info_sort < 0:
            col = self.rich_model.get_column_by_name("order")
        else:
            col = self.rich_model.get_column(info_sort)

        if col.attr:
            node.set_attr("info_sort", col.attr)
            node.set_attr("info_sort_dir", sort_dir)


    def load_sorting(self, node, model):
        """Load sorting information from node"""

        info_sort = node.get_attr("info_sort", "order")
        sort_dir = node.get_attr("info_sort_dir", 1)
            
        if sort_dir:
            sort_dir = gtk.SORT_ASCENDING
        else:
            sort_dir = gtk.SORT_DESCENDING            

        # default sorting
        if info_sort == "":
            info_sort = "order"

        # TODO: do not rely on *_sort convention
        for col in self.rich_model.get_columns():
            if info_sort == col.attr and col.name.endswith("_sort"):
                model.set_sort_column_id(col.pos, sort_dir)

        self._update_reorder()

    
    def set_status(self, text, bar="status"):
        if self.on_status:
            self.on_status(text, bar=bar)


    def _on_node_changed_end(self, model, nodes):
        basetreeview.KeepNoteBaseTreeView._on_node_changed_end(self, model, nodes)

        # make sure root is always expanded
        if self.rich_model.get_nested():
            # determine root set
            child = model.iter_children(None)
            while child is not None:
                self.expand_row(model.get_path(child), False)
                child = model.iter_next(child)

    def _on_listview_row_expanded(self, treeview, it, path):
        """Callback for row expand"""
        self.display_page_count()
        
    
    def _on_listview_row_collapsed(self, treeview, it, path):
        self.display_page_count()






'''
        # title column
        title_column = gtk.TreeViewColumn()
        title_column.set_title(_("Title"))
        title_column.set_sort_column_id(
            self.rich_model.get_column_by_name("title_sort").pos)

        title_column.set_property("sizing", gtk.TREE_VIEW_COLUMN_FIXED)
        title_column.set_property("resizable", True)
        title_column.set_min_width(10)
        title_column.set_fixed_width(250)

        # title icon
        cell_icon = gtk.CellRendererPixbuf()
        title_column.pack_start(cell_icon, False)
        title_column.add_attribute(cell_icon, 'pixbuf',
            self.rich_model.get_column_by_name("icon").pos)
        title_column.add_attribute(cell_icon, 'pixbuf-expander-open',
            self.rich_model.get_column_by_name("icon_open").pos)

        # title text
        title_text = gtk.CellRendererText()
        title_column.pack_start(title_text, True)
        title_text.set_fixed_height_from_font(1)
        title_text.connect("edited", lambda r,p,t: self.on_edit_attr(
            r, p, "title", t, validate=lambda t: t != ""))
        title_text.connect("editing-started", self.on_editing_started)
        title_text.connect("editing-canceled", self.on_editing_canceled)        
        title_text.set_property("editable", True)
        title_column.add_attribute(title_text, 'text',
            self.rich_model.get_column_by_name("title").pos)
        
        self.append_column(title_column)

        # save references
        self.title_text = title_text
        self.title_column = title_column
'''        
