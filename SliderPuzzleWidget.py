# Copyright 2007 World Wide Workshop Foundation
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
#
# If you find this activity useful or end up using parts of it in one of your
# own creations we would love to hear from you at info@WorldWideWorkshop.org !
#

import pygtk
pygtk.require('2.0')
import gtk, gobject
import pango
import md5
import logging

from mamamedia_modules import utils

#from utils import load_image, calculate_matrix, debug, SliderCreator, trace

from types import TupleType, ListType
from random import random
from time import time
from math import sqrt
from cStringIO import StringIO
import os

###
# General Information
###

up_key =    ['Up', 'KP_Up', 'KP_8']
down_key =  ['Down', 'KP_Down', 'KP_2']
left_key =  ['Left', 'KP_Left', 'KP_4']
right_key = ['Right', 'KP_Right', 'KP_6']

SLIDE_UP = 1
SLIDE_DOWN = 2
SLIDE_LEFT = 3
SLIDE_RIGHT = 4

def calculate_matrix (pieces):
    """ Given a number of pieces, calculate the best fit 2 dimensional matrix """
    rows = int(sqrt(pieces))
    cols = int(float(pieces) / rows)
    return rows*cols, rows, cols


class SliderCreator (gtk.gdk.Pixbuf):
    def __init__ (self, width, height, fname=None, tlist=None): #tlist):
        if width == -1:
            width = 564
        if height == -1:
            height = 564
        super(SliderCreator, self).__init__(gtk.gdk.COLORSPACE_RGB, False, 8, width, height)
        if tlist is None:
          items = []
          cmds = file(fname).readlines()
          if len(cmds) > 1:
              _x_ = eval(cmds[0])
              for i in range(16):
                  items.append(_x_)
                  _x_ = eval(cmds[1])
        else:
            items = tlist
        self.width = width
        self.height = height
        self.tlist = items
        self.prepare_stringed(2,2)

    #def scale_simple (self, w,h,m):
    #    return SliderCreator(w,h,tlist=self.tlist)

    #def subpixbuf (self, x,y,w,h):
    #    return SliderCreator(w,h,tlist=self.tlist)

    @classmethod
    def can_handle(klass, fname):
        return fname.lower().endswith('.sequence')

    def prepare_stringed (self, rows, cols):
        # We use a Pixmap as offscreen drawing canvas
        cm = gtk.gdk.colormap_get_system()
        pm = gtk.gdk.Pixmap(None, self.width, self.height, cm.get_visual().depth)
        #pangolayout = pm.create_pango_layout("")
        font_size = int(self.width / cols / 4)
        l = gtk.Label()
        pangolayout = pango.Layout(l.create_pango_context())
        pangolayout.set_font_description(pango.FontDescription("sans bold %i" % font_size))
        gc = pm.new_gc()
        gc.set_colormap(gtk.gdk.colormap_get_system())
        color = cm.alloc_color('white')
        gc.set_foreground(color)
        pm.draw_rectangle(gc, True, 0, 0, self.width, self.height)
        color = cm.alloc_color('black')
        gc.set_foreground(color)

        sw, sh = (self.width / cols), (self.height / rows)
        item = iter(self.tlist)
        for r in range(rows):
            for c in range(cols):
                px = sw * c
                py = sh * r
                #if c > 0 and r > 0:
                #    pm.draw_line(gc, px, 0, px, self.height-1)
                #    pm.draw_line(gc, 0, py, self.width-1, py)
                pangolayout.set_text(str(item.next()))
                pe = pangolayout.get_pixel_extents()
                pe = pe[1][2]/2, pe[1][3]/2
                pm.draw_layout(gc, px + (sw / 2) - pe[0],  py + (sh / 2) - pe[1], pangolayout)
        self.get_from_drawable(pm, cm, 0, 0, 0, 0, -1, -1)

utils.register_image_type(SliderCreator)

###
# Game Logic
###

class MatrixPosition (object):
    """ Helper class to hold a x/y coordinate, and move it by passing a direction,
    taking care of enforcing boundaries as needed.
    The x and y coords are 0 based. """
    def __init__ (self, rowsize, colsize, x=0, y=0):
        self.rowsize = rowsize
        self.colsize = colsize
        self.x = min(x, colsize-1)
        self.y = min(y, rowsize-1)

    def __eq__ (self, other):
        if isinstance(other, (TupleType, ListType)) and len(other) == 2:
            return self.x == other[0] and self.y == other[1]
        return False

    def __ne__ (self, other):
        return not self.__eq__ (other)

    def bottom_right (self):
        """ Move to the lower right position of the matrix, having 0,0 as the top left corner """
        self.x = self.colsize - 1
        self.y = self.rowsize-1

    def move (self, direction, count=1):
        """ Moving direction is actually the opposite of what is passed.
        We are moving the hole position, so if you slice a piece down into the hole,
        that hole is actually moving up.
        Returns bool, false if we can't move in the requested direction."""
        if direction == SLIDE_UP and self.y < self.rowsize-1:
            self.y += 1
            return True
        if direction == SLIDE_DOWN and self.y > 0:
            self.y -= 1
            return True
        if direction == SLIDE_LEFT and self.x < self.colsize-1:
            self.x += 1
            return True
        if direction == SLIDE_RIGHT and self.x > 0:
            self.x -= 1
            return True
        return False

    def clone (self):
        return MatrixPosition(self.rowsize, self.colsize, self.x, self.y)

    def _freeze (self):
        return (self.rowsize, self.colsize, self.x, self.y)

    def _thaw (self, obj):
        if obj is not None:
            self.rowsize, self.colsize, self.x, self.y = obj
        

class SliderPuzzleMap (object):
    """ This class holds the game logic.
    The current pieces position is held in self.pieces_map[YROW][XROW].
    """
    def __init__ (self, pieces=9, move_cb=None):
        self.reset(pieces)
        self.move_cb = move_cb
        self.solved = True

    def reset (self, pieces=9):
        self.pieces, self.rowsize, self.colsize = calculate_matrix(pieces)
        pieces_map = range(1,self.pieces+1)
        self.pieces_map = []
        for i in range(self.rowsize):
            self.pieces_map.append(pieces_map[i*self.colsize:(i+1)*self.colsize])
        self.hole_pos = MatrixPosition(self.rowsize, self.colsize)
        self.hole_pos.bottom_right()
        self.solved_map = [list(x) for x in self.pieces_map]
        self.solved_map[-1][-1] = None

    def randomize (self):
        """ To make sure the randomization is solvable, we don't simply shuffle the numbers.
        We move the hole in random directions through a finite number of iteractions. """
        # Remove the move callback temporarily
        cb = self.move_cb
        self.move_cb = None

        iteractions = self.rowsize * self.colsize * (int(100*random())+1)

        t = time()
        for i in range(iteractions):
            while not (self.do_move(int(4*random())+1)):
                pass

        t = time() - t

        # Now move the hole to the bottom right
        for x in range(self.colsize-self.hole_pos.x-1):
            self.do_move(SLIDE_LEFT)
        for y in range(self.rowsize-self.hole_pos.y-1):
            self.do_move(SLIDE_UP)

        # Put the callback where it was
        self.move_cb = cb
        self.solved = False

    def do_move (self, slide_direction):
        """
        The moves are relative to the moving piece:
        
        >>> jm = SliderPuzzleMap()
        >>> jm.debug_map()
        1 2 3
        4 5 6
        7 8 *
        >>> jm.do_move(SLIDE_DOWN)
        True
        >>> jm.debug_map() # DOWN
        1 2 3
        4 5 *
        7 8 6
        >>> jm.do_move(SLIDE_RIGHT)
        True
        >>> jm.debug_map() # RIGHT
        1 2 3
        4 * 5
        7 8 6
        >>> jm.do_move(SLIDE_UP)
        True
        >>> jm.debug_map() # UP
        1 2 3
        4 8 5
        7 * 6
        >>> jm.do_move(SLIDE_LEFT)
        True
        >>> jm.debug_map() # LEFT
        1 2 3
        4 8 5
        7 6 *

        We can't move over the matrix edges:

        >>> jm.do_move(SLIDE_LEFT)
        False
        >>> jm.debug_map() # LEFT
        1 2 3
        4 8 5
        7 6 *
        >>> jm.do_move(SLIDE_UP)
        False
        >>> jm.debug_map() # UP
        1 2 3
        4 8 5
        7 6 *
        >>> jm.do_move(SLIDE_RIGHT)
        True
        >>> jm.do_move(SLIDE_RIGHT)
        True
        >>> jm.do_move(SLIDE_RIGHT)
        False
        >>> jm.debug_map() # RIGHT x 3
        1 2 3
        4 8 5
        * 7 6
        >>> jm.do_move(SLIDE_DOWN)
        True
        >>> jm.do_move(SLIDE_DOWN)
        True
        >>> jm.do_move(SLIDE_DOWN)
        False
        >>> jm.debug_map() # DOWN x 3
        * 2 3
        1 8 5
        4 7 6
       """
        # What piece are we going to move?
        old_hole_pos = self.hole_pos.clone()
        if self.hole_pos.move(slide_direction):
            # Move was a success, now update the map
            self.pieces_map[old_hole_pos.y][old_hole_pos.x] = self.pieces_map[self.hole_pos.y][self.hole_pos.x]
            self.is_solved()
            if self.move_cb is not None:
                self.move_cb(self.hole_pos.x, self.hole_pos.y, old_hole_pos.x, old_hole_pos.y)
            return True
        return False

    def do_move_piece (self, piece):
        """ Move the piece (1 based index) into the hole, if possible
        >>> jm = SliderPuzzleMap()
        >>> jm.debug_map()
        1 2 3
        4 5 6
        7 8 *
        >>> jm.do_move_piece(6)
        True
        >>> jm.debug_map() # Moved 6
        1 2 3
        4 5 *
        7 8 6
        >>> jm.do_move_piece(2)
        False
        >>> jm.debug_map() # No move
        1 2 3
        4 5 *
        7 8 6

        Return True if a move was done, False otherwise.
        """
        for y in range(self.rowsize):
            for x in range(self.colsize):
                if self.pieces_map[y][x] == piece:
                    if self.hole_pos.x == x:
                        if abs(self.hole_pos.y-y) == 1:
                            return self.do_move(self.hole_pos.y > y and SLIDE_DOWN or SLIDE_UP)
                    elif self.hole_pos.y == y:
                        if abs(self.hole_pos.x-x) == 1:
                            return self.do_move(self.hole_pos.x > x and SLIDE_RIGHT or SLIDE_LEFT)
                    else:
                        return False
        return False

    def is_hole_at (self, x, y):
        """
        >>> jm = SliderPuzzleMap()
        >>> jm.debug_map()
        1 2 3
        4 5 6
        7 8 *
        >>> jm.is_hole_at(2,2)
        True
        >>> jm.is_hole_at(0,0)
        False
        """
        return self.hole_pos == (x,y)

    def is_solved (self):
        """
        >>> jm = SliderPuzzleMap()
        >>> jm.do_move_piece(6)
        True
        >>> jm.is_solved()
        False
        >>> jm.do_move_piece(6)
        True
        >>> jm.is_solved()
        True
        """
        if self.hole_pos != (self.colsize-1, self.rowsize-1):
            return False
        self.pieces_map[self.hole_pos.y][self.hole_pos.x] = None
        self.solved = self.pieces_map == self.solved_map
        return self.solved
        
        

    def get_cell_at (self, x, y):
        if x < 0 or x >= self.colsize or y < 0 or y >= self.rowsize or self.is_hole_at(x,y):
            return None
        return self.pieces_map[y][x]

    def debug_map (self):
        for y in range(self.rowsize):
            for x in range(self.colsize):
                if self.hole_pos == (x,y):
                    logging.debug("*")
                else:
                    logging.debug(self.pieces_map[y][x])

    def __call__ (self):
        self.debug_map()

    def _freeze (self):
        return {'pieces': self.pieces, 'rowsize': self.rowsize, 'colsize': self.colsize,
                'pieces_map': self.pieces_map, 'hole_pos_freeze': self.hole_pos._freeze()}

    def _thaw (self, obj):
        for k in obj.keys():
            if hasattr(self, k):
                setattr(self, k, obj[k])
        self.hole_pos._thaw(obj.get('hole_pos_freeze', None))


###
# Widget Definition
###

class SliderPuzzleWidget (gtk.Table):
    __gsignals__ = {'solved' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
                    'shuffled' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
                    'moved' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),}
    
    def __init__ (self, pieces=9, width=480, height=480):
        self.jumbler = SliderPuzzleMap(pieces, self.jumblermap_piece_move_cb)
        # We take this from the jumbler object because it may have altered our requested value
        gtk.Table.__init__(self, self.jumbler.rowsize, self.jumbler.colsize)
        self.image = None #gtk.Image()
        self.width = width
        self.height = height
        self.set_size_request(width, height)
        self.filename = None

    def prepare_pieces (self):
        """ set up a list of UI objects that will serve as pieces, ordered correctly """
        self.pieces = []
        if self.image is None:
        #    pb = self.image.get_pixbuf()
        #if self.image is None or pb is None:
            for i in range(self.jumbler.pieces):
                self.pieces.append(gtk.Button(str(i+1)))
                self.pieces[-1].connect("button-release-event", self.process_mouse_click, i+1)
                self.pieces[-1].show()
        else:
            if isinstance(self.image, SliderCreator):
                # ask for image creation
                self.image.prepare_stringed(self.jumbler.rowsize, self.jumbler.colsize)
        
            w = self.image.get_width() / self.jumbler.colsize
            h = self.image.get_height() / self.jumbler.rowsize
            for y in range(self.jumbler.rowsize):
                for x in range(self.jumbler.colsize):
                    img = gtk.Image()
                    img.set_from_pixbuf(self.image.subpixbuf(x*w, y*h, w-1, h-1))
                    img.show()
                    self.pieces.append(gtk.EventBox())
                    self.pieces[-1].add(img)
                    self.pieces[-1].connect("button-press-event", self.process_mouse_click, (y*self.jumbler.colsize)+x+1)
                    self.pieces[-1].show()
            self.set_row_spacings(1)
            self.set_col_spacings(1)

    @utils.trace
    def full_refresh (self):
        # Delete everything
        self.foreach(self.remove)
        self.prepare_pieces()
        # Add the pieces in their respective places
        for y in range(self.jumbler.rowsize):
            for x in range(self.jumbler.colsize):
                pos = self.jumbler.get_cell_at(x, y)
                if pos is not None:
                    self.attach(self.pieces[pos-1], x, x+1, y, y+1)

    def process_mouse_click (self, b, e, i):
        # i is the 1 based index of the piece
        self.jumbler.do_move_piece(i)

    def process_key (self, w, e):
        if self.get_parent() == None:
            return False
        k = gtk.gdk.keyval_name(e.keyval)
        if k in up_key:
            self.jumbler.do_move(SLIDE_UP)
            return True
        if k in down_key:
            self.jumbler.do_move(SLIDE_DOWN)
            return True
        if k in left_key:
            self.jumbler.do_move(SLIDE_LEFT)
            return True
        if k in right_key:
            self.jumbler.do_move(SLIDE_RIGHT)
            return True
        return False

    ### SliderPuzzleMap specific callbacks ###

    def jumblermap_piece_move_cb (self, hx, hy, px, py):
        if not hasattr(self, 'pieces'):
            return
        piece = self.pieces[self.jumbler.get_cell_at(px, py)-1]
        self.remove(piece)
        self.attach(piece, px, px+1, py, py+1)
        self.emit("moved")
        if self.jumbler.solved:
            self.emit("solved")

    ### Parent callable interface ###

    def get_nr_pieces (self):
        return self.jumbler.pieces

    @utils.trace
    def set_nr_pieces (self, nr_pieces):
        self.jumbler.reset(nr_pieces)
        self.resize(self.jumbler.rowsize, self.jumbler.colsize)
        self.randomize()

    @utils.trace
    def randomize (self):
        """ Jumble the SliderPuzzle """
        self.jumbler.randomize()
        self.full_refresh()
        self.emit("shuffled")

    @utils.trace
    def load_image (self, image, width=0, height=0):
        """ Loads an image from the file.
        width and height are processed as follows:
          -1 : follow the loaded image size
           0 : follow the size set on widget instantiation
           * : use that specific size"""
        if width == 0:
            width = self.width
        if height == 0:
            height = self.height
        if not isinstance(image, SliderCreator):
            self.image = utils.resize_image(image, width, height)
        else:
            self.image = image
        self.filename = True
        self.full_refresh()

    def set_image (self, image):
        # image is a pixbuf!
        self.image = image
        self.filename = True

    def set_image_from_str (self, image):
        fn = os.tempnam() 
        f = file(fn, 'w+b')
        f.write(image)
        f.close()
        i = gtk.Image()
        i.set_from_file(fn)
        os.remove(fn)
        self.image = i.get_pixbuf()
        self.filename = True

    def show_image (self):
        """ Shows the full image, used as visual clue for solved puzzle """
        # Delete everything
        self.foreach(self.remove)
        if hasattr(self, 'pieces'):
            del self.pieces
        # Resize to a single cell and use that for the image
        self.resize(1,1)
        img = gtk.Image()
        img.set_from_pixbuf(self.image)
        self.attach(img, 0,1,0,1)
        img.show()

    def get_image_as_png (self, cb=None):
        if self.image is None:
            return None
        rv = None
        if cb is None:
            rv = StringIO()
            cb = rv.write
        self.image.save_to_callback(cb, "png")
        if rv is not None:
            return rv.getvalue()
        else:
            return True

    def _freeze (self, journal=True):
        """ returns a json writable object representation capable of being used to restore our current status """
        if journal:
            return {'jumbler': self.jumbler._freeze(),
                    'image': self.get_image_as_png(),
                    }
        else:
            return {'jumbler': self.jumbler._freeze()}

    def _thaw (self, obj):
        """ retrieves a frozen status from a python object, as per _freeze """
        logging.debug(obj['jumbler'])
        self.jumbler._thaw(obj['jumbler'])
        if obj.has_key('image') and obj['image'] is not None:
            self.set_image_from_str(obj['image'])
            del obj['image']
        self.full_refresh()

def _test():
    import doctest
    doctest.testmod()

if __name__ == '__main__':
    _test()
