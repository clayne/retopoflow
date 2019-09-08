'''
Copyright (C) 2019 CG Cookie
http://cgcookie.com
hello@cgcookie.com

Created by Jonathan Denning, Jonathan Williamson, and Patrick Moore

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
'''

import random

from .contours_ops import Contours_Ops
from .contours_utils import (
    find_loops,
    find_strings,
    loop_plane,
    Contours_Loop,
)

from ..rftool import RFTool

from ...addon_common.common.maths import Point, Normal
from ...addon_common.common.utils import iter_pairs

class RFTool_Contours(RFTool):
    name        = 'Contours'
    description = 'Retopologize cylindrical forms, like arms and legs'
    icon        = 'contours_32.png'


class Contours(RFTool_Contours, Contours_Ops):
    def init(self):
        self.show_cut = False
        self.show_arrows = False
        self.pts = []
        self.cut_pts = []
        self.connected = False
        self.cuts = []

    def update_change(self):
        sel_edges = self.rfcontext.get_selected_edges()
        #sel_faces = self.rfcontext.get_selected_faces()

        # find verts along selected loops and strings
        sel_loops = find_loops(sel_edges)
        sel_strings = find_strings(sel_edges)

        # filter out any loops or strings that are in the middle of a selected patch
        def in_middle(bmvs, is_loop):
            return any(len(bmv0.shared_edge(bmv1).link_faces) > 1 for bmv0,bmv1 in iter_pairs(bmvs, is_loop))
        sel_loops = [loop for loop in sel_loops if not in_middle(loop, True)]
        sel_strings = [string for string in sel_strings if not in_middle(string, False)]

        # filter out long loops that wrap around patches, sharing edges with other strings
        bmes = {bmv0.shared_edge(bmv1) for string in sel_strings for bmv0,bmv1 in iter_pairs(string,False)}
        sel_loops = [loop for loop in sel_loops if not any(bmv0.shared_edge(bmv1) in bmes for bmv0,bmv1 in iter_pairs(loop,True))]

        mirror_mod = self.rfcontext.rftarget.mirror_mod
        symmetry_threshold = mirror_mod.symmetry_threshold
        def get_string_length(string):
            nonlocal mirror_mod, symmetry_threshold
            c = len(string)
            if c == 0: return 0
            touches_mirror = False
            (x0,y0,z0),(x1,y1,z1) = string[0].co,string[-1].co
            if mirror_mod.x:
                if abs(x0) < symmetry_threshold or abs(x1) < symmetry_threshold:
                    c = (c - 1) * 2
                    touches_mirror = True
            if mirror_mod.y:
                if abs(y0) < symmetry_threshold or abs(y1) < symmetry_threshold:
                    c = (c - 1) * 2
                    touches_mirror = True
            if mirror_mod.z:
                if abs(z0) < symmetry_threshold or abs(z1) < symmetry_threshold:
                    c = (c - 1) * 2
                    touches_mirror = True
            if not touches_mirror: c -= 1
            return c

        self.loops_data = [{
            'loop': loop,
            'plane': loop_plane(loop),
            'count': len(loop),
            'radius': loop_radius(loop),
            'cl': Contours_Loop(loop, True),
            } for loop in sel_loops]
        self.strings_data = [{
            'string': string,
            'plane': loop_plane(string),
            'count': get_string_length(string),
            'cl': Contours_Loop(string, False),
            } for string in sel_strings]
        self.sel_loops = [Contours_Loop(loop, True) for loop in sel_loops]

    @RFTool_Contours.FSM_State('main')
    def main(self) :
        if self.rfcontext.actions.pressed({'select', 'select add'}):
            return self.rfcontext.setup_selection_painting(
                'edge',
                fn_filter_bmelem=self.filter_edge_selection,
                kwargs_select={'supparts': False},
                kwargs_deselect={'subparts': False},
            )
        if self.rfcontext.actions.pressed('N'):
            print('N')
            self.rfcontext.rftarget.new_vert(
                Point((random.random(), random.random(), random.random())),
                Normal((1, 0, 0))
            )
            self.rfcontext.dirty()

    def filter_edge_selection(self, bme, no_verts_select=True, ratio=0.33):
        if bme.select:
            # edge is already selected
            return True
        bmv0, bmv1 = bme.verts
        s0, s1 = bmv0.select, bmv1.select
        if s0 and s1:
            # both verts are selected, so return True
            return True
        if not s0 and not s1:
            if no_verts_select:
                # neither are selected, so return True by default
                return True
            else:
                # return True if none are selected; otherwise return False
                return self.rfcontext.none_selected()
        # if mouse is at least a ratio of the distance toward unselected vert, return True
        if s1: bmv0, bmv1 = bmv1, bmv0
        p = self.rfcontext.actions.mouse
        p0 = self.rfcontext.Point_to_Point2D(bmv0.co)
        p1 = self.rfcontext.Point_to_Point2D(bmv1.co)
        v01 = p1 - p0
        l01 = v01.length
        d01 = v01 / l01
        dot = d01.dot(p - p0)
        return dot / l01 > ratio