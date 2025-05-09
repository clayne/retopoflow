/*
Copyright (C) 2023 CG Cookie
http://cgcookie.com
hello@cgcookie.com

Created by Jonathan Denning

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
*/

#define BMESH_FACE

#include "bmesh_render_prefix.glsl"


/////////////////////////////////////////////////////////////////////////
// vertex shader

in vec4  vert_pos;       // position wrt model
in vec4  vert_norm;      // normal wrt model
in float selected;       // is face selected?  0=no; 1=yes
in float pinned;         // is face pinned?  0=no; 1=yes

out vec4 vPPosition;        // final position (projected)
out vec4 vCPosition;        // position wrt camera
out vec4 vTPosition;        // position wrt target
out vec4 vCTPosition_x;     // position wrt target camera
out vec4 vCTPosition_y;     // position wrt target camera
out vec4 vCTPosition_z;     // position wrt target camera
out vec4 vPTPosition_x;     // position wrt target projected
out vec4 vPTPosition_y;     // position wrt target projected
out vec4 vPTPosition_z;     // position wrt target projected
out vec3 vCNormal;          // normal wrt camera
out vec4 vColor;            // color of geometry (considers selection)

void main() {
    //vec4 off = vec4(radius * (vert_dir0 * vert_offset.x + vert_dir1 * vert_offset.y) / screen_size, 0, 0);

    vec4 pos = get_pos(vec3(vert_pos));
    vec3 norm = normalize(vec3(vert_norm) * vec3(options.vert_scale));

    vec4 wpos = push_pos(options.matrix_m * pos);
    vec3 wnorm = normalize(mat4_to_mat3(options.matrix_mn) * norm);

    vec4 tpos = options.matrix_ti * wpos;
    vec3 tnorm = vec3(
        dot(wnorm, vec3(options.mirror_x)),
        dot(wnorm, vec3(options.mirror_y)),
        dot(wnorm, vec3(options.mirror_z)));

    vCPosition  = options.matrix_v * wpos;
    vPPosition  = xyz4(options.matrix_p * options.matrix_v * wpos);

    vCNormal    = normalize(mat4_to_mat3(options.matrix_vn) * wnorm);

    vTPosition    = tpos;
    vCTPosition_x = options.matrix_v * options.matrix_t * vec4(0.0, tpos.y, tpos.z, 1.0);
    vCTPosition_y = options.matrix_v * options.matrix_t * vec4(tpos.x, 0.0, tpos.z, 1.0);
    vCTPosition_z = options.matrix_v * options.matrix_t * vec4(tpos.x, tpos.y, 0.0, 1.0);
    vPTPosition_x = options.matrix_p * vCTPosition_x;
    vPTPosition_y = options.matrix_p * vCTPosition_y;
    vPTPosition_z = options.matrix_p * vCTPosition_z;

    gl_Position = vPPosition;

    vColor = options.color_normal;

    if(use_selection() && selected > 0.5) vColor = mix(vColor, options.color_selected, 0.75);
    if(use_pinned()    && pinned   > 0.5) vColor = mix(vColor, options.color_pinned,   0.75);

    vColor.a *= 1.0 - options.hidden.x;

    if(debug_invert_backfacing && vCNormal.z < 0.0) {
        vColor = vec4(vec3(1,1,1) - vColor.rgb, vColor.a);
    }
}



/////////////////////////////////////////////////////////////////////////
// fragment shader

in vec4 vPPosition;        // final position (projected)
in vec4 vCPosition;        // position wrt camera
in vec4 vTPosition;        // position wrt target
in vec4 vCTPosition_x;     // position wrt target camera
in vec4 vCTPosition_y;     // position wrt target camera
in vec4 vCTPosition_z;     // position wrt target camera
in vec4 vPTPosition_x;     // position wrt target projected
in vec4 vPTPosition_y;     // position wrt target projected
in vec4 vPTPosition_z;     // position wrt target projected
in vec3 vCNormal;          // normal wrt camera
in vec4 vColor;            // color of geometry (considers selection)

out vec4 outColor;
out float gl_FragDepth;

void main() {
    float clip  = options.clip.y - options.clip.x;
    float focus = (view_distance() - options.clip.x) / clip + 0.04;
    vec3  rgb   = vColor.rgb;
    float alpha = vColor.a;

    if(vCNormal.z < 0) { discard; return; }

    if(is_view_perspective()) {
        // perspective projection
        vec3 v = xyz3(vCPosition);
        float l = length(v);
        float l_clip = (l - options.clip.x) / clip;
        float d = -dot(vCNormal, v) / l;
        if(d <= 0.0) {
            if(cull_backfaces()) {
                alpha = 0.0;
                discard;
                return;
            } else {
                alpha *= min(1.0, alpha_backface());
            }
        }
    } else {
        // orthographic projection
        vec3 v = vec3(0, 0, clip * 0.5); // + vCPosition.xyz / vCPosition.w;
        float l = length(v);
        float l_clip = (l - options.clip.x) / clip;
        float d = dot(vCNormal, v) / l;
        if(d <= 0.0) {
            if(cull_backfaces()) {
                alpha = 0.0;
                discard;
                return;
            } else {
                alpha *= min(1.0, alpha_backface());
            }
        }
    }

    alpha *= min(1.0, pow(max(vCNormal.z, 0.01), 0.25));
    outColor = coloring(vec4(rgb, alpha));
    // https://wiki.blender.org/wiki/Reference/Release_Notes/2.83/Python_API
    outColor = blender_srgb_to_framebuffer_space(outColor);
}
