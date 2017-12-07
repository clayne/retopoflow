'''
Copyright (C) 2017 CG Cookie
http://cgcookie.com
hello@cgcookie.com

Created by Jonathan Denning, Jonathan Williamson

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

import os
import bpy
import bgl
import blf
import math
import time
import urllib

from .rftool import RFTool

from ..lib.classes.profiler.profiler import profiler
from ..common.maths import Point, Point2D, Vec2D, XForm, clamp
from ..common.ui import Drawing
from ..common.ui import (
    UI_WindowManager,
    UI_Button, UI_Image,
    UI_Options,
    UI_Checkbox, UI_Checkbox2,
    UI_Label, UI_WrappedLabel, UI_Markdown,
    UI_Spacer, UI_Rule,
    UI_Container, UI_Collapsible, UI_EqualContainer,
    UI_IntValue,
    GetSet,
    )
from ..lib import common_drawing_bmesh as bmegl

from ..options import (
    retopoflow_version,
    retopoflow_profiler,
    retopoflow_issues_url,
    retopoflow_tip_url,
    options,
    firsttime_message,
    )


class RFContext_Drawing:
    def quit(self): self.exit = True
    
    def set_symmetry(self, axis, enable):
        if enable: self.rftarget.enable_symmetry(axis)
        else: self.rftarget.disable_symmetry(axis)
        #for rfs in self.rfsources: rfs.dirty()
        self.rftarget.dirty()
    def get_symmetry(self, axis): return self.rftarget.has_symmetry(axis)
    
    def toggle_tool_help(self):
        if self.window_help.visible:
            self.window_help.visible = False
            self.window_manager.clear_active()
        else:
            self.ui_helplabel.set_markdown(self.tool.helptext())
            self.window_help.visible = True
    
    def alert_assert(self, must_be_true_condition, title=None, message=None, throw=True):
        if must_be_true_condition: return True
        self.alert_user(title=title, message=message, level='assert')
        if throw: assert False
        return False
    
    def alert_user(self, title=None, message=None, level=None):
        level = level.lower() if level else 'note'
        blender_version = '%d.%02d.%d' % bpy.app.version
        if level in {'warning'}:
            bgcolor = (0.35, 0.25, 0.15, 0.95)
            title = 'Warning' + (': %s' % title if title else '')
        elif level in {'error'}:
            bgcolor = (0.30, 0.15, 0.15, 0.95)
            title = 'Error' + (': %s' % title if title else '!')
        elif level in {'assert', 'exception'}:
            if level == 'assert':
                bgcolor = (0.30, 0.15, 0.15, 0.95)
                title = 'Assert Error' + (': %s' % title if title else '!')
                desc = 'An internal assertion has failed.'
            else:
                bgcolor = (0.15, 0.07, 0.07, 0.95)
                title = 'Unhandled Exception Caught' + (': %s' % title if title else '!')
                desc = 'An unhandled exception was thrown.'
            message_orig = message
            msg = '\n'.join([
                desc,
                'This was unexpected.',
                'If this happens again, please report as bug so we can fix it.',
                '',
                'RetopoFlow: %s, Blender: %s' % (retopoflow_version, blender_version),
                ])
            message = msg + (('\n\n%s' % message) if message else '')
        else:
            bgcolor = (0.20, 0.20, 0.30, 0.95)
            title = 'Note' + (': %s' % title if title else '')
            message = message or 'a note'
        
        def close():
            nonlocal win
            self.window_manager.delete_window(win)
        def screenshot():
            ss_filename = options['screenshot filename']
            if bpy.data.filepath == '':
                # startup file
                filepath = os.path.abspath(ss_filename)
            else:
                # loaded .blend file
                filepath = os.path.split(os.path.abspath(bpy.data.filepath))[0]
                filepath = os.path.join(filepath, ss_filename)
            bpy.ops.screen.screenshot(filepath=filepath)
            self.alert_user(message='Saved screenshot to "%s"' % filepath)
            
        def report():
            data = {
                'title': '%s: %s' % (self.tool.name(), title),
                'body': '\n'.join([
                    'Please tell us what you were trying to do, what you expected RetopoFlow to do, and what actually happened.',
                    'Provide as much information as you can so that we can reproduce the problem and fix it.',
                    'Screenshots and .blend files are very helpful.'
                    'Also, change the title of this bug report to something descriptive and helpful.',
                    'Thank you!',
                    '-------------------------------------',
                    'RetopoFlow: %s' % retopoflow_version,
                    'Blender: %s' % blender_version,
                    ] + (['',message_orig] if message_orig else []))
            }
            url = '%s?%s' % (options['github new issue url'], urllib.parse.urlencode(data))
            bpy.ops.wm.url_open(url=url)
        
        def event_handler(context, event):
            if event.type == 'ESC' and event.value == 'RELEASE':
                close()
        
        opts = {
            'sticky': 5,
            'movable': False,
            'bgcolor': bgcolor,
            'event handler': event_handler,
            }
        win = self.window_manager.create_window(title, opts)
        win.add(UI_Rule())
        win.add(UI_Markdown(message, min_size=Vec2D((300,36))))
        win.add(UI_Rule())
        container = win.add(UI_EqualContainer(margin=1, vertical=False), footer=True)
        container.add(UI_Button('Close', close, align=0, bgcolor=(0.5,0.5,0.5,0.4), margin=1))
        if level in {'assert', 'exception'}:
            container.add(UI_Button('Screenshot', screenshot, align=0, bgcolor=(0.5,0.5,0.5,0.4), margin=1))
            container.add(UI_Button('Report', report, align=0, bgcolor=(0.5,0.5,0.5,0.4), margin=1))
        
    
    def _init_drawing(self):
        self.drawing = Drawing.get_instance()
        self.window_manager = UI_WindowManager()
        
        def get_selected_tool():
            return self.tool.name()
        def set_selected_tool(name):
            for ids,rft in RFTool.get_tools():
                if rft.bl_label == name:
                    self.set_tool(rft.rft_class())
        def update_tool_collapsed():
            b = options['tools_min']
            self.tool_min.visible = b
            self.tool_max.visible = not b
        def get_tool_collapsed():
            update_tool_collapsed()
            return options['tools_min']
        def set_tool_collapsed(b):
            options['tools_min'] = b
            update_tool_collapsed()
        def show_reporting():
            options['welcome'] = True
            self.window_welcome.visible = options['welcome']
        def hide_reporting():
            options['welcome'] = False
            self.window_welcome.visible = options['welcome']
            self.window_manager.clear_active()
        
        def open_github():
            bpy.ops.wm.url_open(url=retopoflow_issues_url)
        def open_tip():
            bpy.ops.wm.url_open(url=retopoflow_tip_url)
        
        def get_theme():
            return options['color theme']
        def set_theme(v):
            options['color theme'] = v
            self.replace_opts()
        def reset_options():
            options.reset()
            self.replace_opts()
        def get_instrument(): return options['instrument']
        def set_instrument(v): options['instrument'] = v
        def get_autocollapse(): return options['tools autocollapse']
        def set_autocollapse(v): options['tools autocollapse'] = v
        def update_profiler_visible():
            nonlocal prof_print, prof_reset, prof_disable, prof_enable
            v = profiler.debug
            prof_print.visible = v
            prof_reset.visible = v
            prof_disable.visible = v
            prof_enable.visible = not v
        def enable_profiler():
            profiler.enable()
            update_profiler_visible()
        def disable_profiler():
            profiler.disable()
            update_profiler_visible()
        def get_debug_level():
            return options['debug level']
            # return self.settings.debug
        def set_debug_level(v):
            options['debug level'] = clamp(v, 0, 5)
            #self.settings.debug = v
        
        def wrap_pos_option(key):
            def get():
                v = options[key]
                if type(v) is int: return v
                return Point2D(v)
            def set(v):
                if type(v) is int: options[key] = v
                else: options[key] = tuple(v)
            return GetSet(get, set)
        def wrap_bool_option(key, default_val):
            key = key.lower()
            def get(): return options[key]
            def set(v): options[key] = v
            options.set_default(key, default_val)
            return GetSet(get, set)
        
        self.tool_window = self.window_manager.create_window('Tools', {'fn_pos':wrap_pos_option('tools pos')})
        self.tool_max = UI_Container(margin=0)
        self.tool_min = UI_Container(margin=0, vertical=False)
        self.tool_selection_max = UI_Options(get_selected_tool, set_selected_tool, vertical=True)
        self.tool_selection_min = UI_Options(get_selected_tool, set_selected_tool, vertical=False)
        tools_options = []
        for i,rft_data in enumerate(RFTool.get_tools()):
            ids,rft = rft_data
            self.tool_selection_max.add_option(rft.bl_label, icon=rft.rft_class().get_ui_icon())
            self.tool_selection_min.add_option(rft.bl_label, icon=rft.rft_class().get_ui_icon(), showlabel=False)
            ui_options = rft.rft_class().get_ui_options()
            if ui_options: tools_options.append((rft.bl_label,ui_options))
        get_tool_collapsed()
        self.tool_max.add(self.tool_selection_max)
        
        extra = self.tool_max.add(UI_Container())
        #help_icon = UI_Image('help_32.png')
        #help_icon.set_size(16, 16)
        extra.add(UI_Button('Tool Help', self.toggle_tool_help, align=0, margin=0)) # , icon=help_icon
        extra.add(UI_Button('Collapse', lambda: set_tool_collapsed(True), align=0, margin=0))
        #extra.add(UI_Checkbox('Collapsed', get_tool_collapsed, set_tool_collapsed))
        extra.add(UI_Button('Exit', self.quit, align=0, margin=0))
        self.tool_min.add(self.tool_selection_min)
        self.tool_min.add(UI_Checkbox(None, get_tool_collapsed, set_tool_collapsed))
        self.tool_window.add(self.tool_max)
        self.tool_window.add(self.tool_min)
        
        
        window_info = self.window_manager.create_window('RetopoFlow %s' % retopoflow_version, {'fn_pos':wrap_pos_option('info pos')})
        #window_info.add(UI_Label('RetopoFlow %s' % retopoflow_version, align=0))
        container = window_info.add(UI_Container(margin=0, vertical=False))
        container.add(UI_Button('Welcome!', show_reporting, align=0, margin=0))
        container.add(UI_Button('Report Issue', open_github, align=0, margin=0))
        window_info.add(UI_Button('Buy us a drink', open_tip, align=0, margin=0))
        info_adv = window_info.add(UI_Collapsible('Advanced', collapsed=True))
        
        fps_save = info_adv.add(UI_Container(vertical=False))
        self.window_debug_fps = fps_save.add(UI_Label('fps: 0.00'))
        self.window_debug_save = fps_save.add(UI_Label('save: inf'))
        
        info_adv.add(UI_IntValue('Debug Level', get_debug_level, set_debug_level))
        info_adv.add(UI_Checkbox('Instrument', get_instrument, set_instrument))
        
        if retopoflow_profiler:
            info_profiler = info_adv.add(UI_Collapsible('Profiler', collapsed=True, vertical=False))
            prof_print = info_profiler.add(UI_Button('Print', profiler.printout, align=0))
            prof_reset = info_profiler.add(UI_Button('Reset', profiler.clear, align=0))
            prof_disable = info_profiler.add(UI_Button('Disable', disable_profiler, align=0))
            prof_enable = info_profiler.add(UI_Button('Enable', enable_profiler, align=0))
            update_profiler_visible()
        
        info_adv.add(UI_Button('Reset Options', reset_options, align=0))
        
        window_tool_options = self.window_manager.create_window('Options', {'fn_pos':wrap_pos_option('options pos')})
        
        dd_general = window_tool_options.add(UI_Collapsible('General', fn_collapsed=wrap_bool_option('tools general collapsed', False)))
        dd_general.add(UI_Button('Maximize Area', self.rfmode.ui_toggle_maximize_area, align=0))
        dd_general.add(UI_Button('Snap All Verts', self.snap_all_verts, align=0))
        container_theme = dd_general.add(UI_Container(vertical=False))
        container_theme.add(UI_Label('Theme:', margin=4))
        opt_theme = container_theme.add(UI_Options(get_theme, set_theme, vertical=False, margin=0))
        opt_theme.add_option('Blue', icon=UI_Image('theme_blue.png'), showlabel=False, align=0)
        opt_theme.add_option('Green', icon=UI_Image('theme_green.png'), showlabel=False, align=0)
        opt_theme.add_option('Orange', icon=UI_Image('theme_orange.png'), showlabel=False, align=0)
        opt_theme.set_option(options['color theme'])
        dd_general.add(UI_Checkbox('Auto Collapse Options', get_autocollapse, set_autocollapse))
        
        
        dd_symmetry = window_tool_options.add(UI_Collapsible('Symmetry', equal=True, vertical=False, fn_collapsed=wrap_bool_option('tools symmetry collapsed', True)))
        dd_symmetry.add(UI_Checkbox2('x', lambda: self.get_symmetry('x'), lambda v: self.set_symmetry('x',v), options={'spacing':0}))
        dd_symmetry.add(UI_Checkbox2('y', lambda: self.get_symmetry('y'), lambda v: self.set_symmetry('y',v), options={'spacing':0}))
        dd_symmetry.add(UI_Checkbox2('z', lambda: self.get_symmetry('z'), lambda v: self.set_symmetry('z',v), options={'spacing':0}))
        
        for tool_name,tool_options in tools_options:
            # window_tool_options.add(UI_Spacer(height=5))
            ui_options = window_tool_options.add(UI_Collapsible(tool_name, fn_collapsed=wrap_bool_option('tool %s collapsed' % tool_name, True)))
            for tool_option in tool_options: ui_options.add(tool_option)
        
        self.window_welcome = self.window_manager.create_window('Welcome!', {'sticky':5, 'visible':options['welcome'], 'movable':False, 'bgcolor':(0.2,0.2,0.2,0.95)})
        self.window_welcome.add(UI_Rule())
        self.window_welcome.add(UI_Markdown(firsttime_message))
        self.window_welcome.add(UI_Rule())
        self.window_welcome.add(UI_Button('Close', hide_reporting, align=0, bgcolor=(0.5,0.5,0.5,0.4), margin=2), footer=True)
        
        self.window_help = self.window_manager.create_window('Tool Help', {'sticky':5, 'visible':False, 'movable':False, 'bgcolor':(0.2,0.2,0.2,0.95)})
        self.window_help.add(UI_Rule())
        self.ui_helplabel = UI_Markdown('help text here!')
        # self.window_help.add(UI_Scrollable(self.ui_helplabel))
        self.window_help.add(self.ui_helplabel)
        self.window_help.add(UI_Rule())
        self.window_help.add(UI_Button('Close', self.toggle_tool_help, align=0, bgcolor=(0.5,0.5,0.5,0.4), margin=2), footer=True)

    def get_view_version(self):
        m = self.actions.r3d.view_matrix
        return [v for r in m for v in r]

    def draw_postpixel(self):
        if not self.actions.r3d: return

        wtime,ctime = self.fps_time,time.time()
        self.frames += 1
        if ctime >= wtime + 1:
            self.fps = self.frames / (ctime - wtime)
            self.frames = 0
            self.fps_time = ctime

        bgl.glEnable(bgl.GL_MULTISAMPLE)
        bgl.glEnable(bgl.GL_BLEND)
        bgl.glEnable(bgl.GL_POINT_SMOOTH)

        self.tool.draw_postpixel()
        self.rfwidget.draw_postpixel()
        
        self.window_debug_fps.set_label('fps: %0.2f' % self.fps)
        self.window_debug_save.set_label('save: %0.0f' % (self.time_to_save or float('inf')))
        self.window_manager.draw_postpixel()

    def draw_preview(self):
        if not self.actions.r3d: return
        
        bgl.glEnable(bgl.GL_MULTISAMPLE)
        bgl.glEnable(bgl.GL_BLEND)
        bgl.glEnable(bgl.GL_POINT_SMOOTH)
        bgl.glDisable(bgl.GL_DEPTH_TEST)
        
        bgl.glMatrixMode(bgl.GL_MODELVIEW)
        bgl.glPushMatrix()
        bgl.glLoadIdentity()
        bgl.glMatrixMode(bgl.GL_PROJECTION)
        bgl.glPushMatrix()
        bgl.glLoadIdentity()
        
        bgl.glBegin(bgl.GL_TRIANGLES)
        for i in range(0,360,10):
            r0,r1 = i*math.pi/180.0, (i+10)*math.pi/180.0
            x0,y0 = math.cos(r0)*2,math.sin(r0)*2
            x1,y1 = math.cos(r1)*2,math.sin(r1)*2
            bgl.glColor4f(0,0,0.01,0.0)
            bgl.glVertex2f(0,0)
            bgl.glColor4f(0,0,0.01,0.8)
            bgl.glVertex2f(x0,y0)
            bgl.glVertex2f(x1,y1)
        bgl.glEnd()
        
        bgl.glMatrixMode(bgl.GL_PROJECTION)
        bgl.glPopMatrix()
        bgl.glMatrixMode(bgl.GL_MODELVIEW)
        bgl.glPopMatrix()

    @profiler.profile
    def draw_postview(self):
        if not self.actions.r3d: return
        
        buf_matrix_view = XForm.to_bglMatrix(self.actions.r3d.view_matrix)
        buf_matrix_proj = XForm.to_bglMatrix(self.actions.r3d.window_matrix)

        bgl.glEnable(bgl.GL_MULTISAMPLE)
        bgl.glEnable(bgl.GL_BLEND)
        bgl.glEnable(bgl.GL_POINT_SMOOTH)

        pr = profiler.start('render sources')
        ft = self.rftarget.get_frame()
        for rs,rfs in zip(self.rfsources, self.rfsources_draw):
            fs = rs.get_frame()
            ft_ = fs.w2l_frame(ft)
            rfs.draw(buf_matrix_view, buf_matrix_proj, self.rftarget.symmetry, ft_)
        pr.done()
        
        pr = profiler.start('render target')
        self.rftarget_draw.draw(buf_matrix_view, buf_matrix_proj)
        pr.done()
        
        pr = profiler.start('render other')
        self.tool.draw_postview()
        self.rfwidget.draw_postview()
        pr.done()
