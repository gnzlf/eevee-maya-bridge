// Own D3D11 resources shared between Blender and Maya GL contexts. No pixel readback.
#include <windows.h>
#include <d3d11.h>
#include <dxgi.h>
#include <GL/gl.h>
#include <cstdint>
#include <string>
#include <cstdio>
#include <cstring>

namespace {
thread_local std::string error;
using GLchar = char;
#define API extern "C" __declspec(dllexport)
#define FN(ret, name, ...) using T_##name = ret (WINAPI*)(__VA_ARGS__); T_##name name = nullptr
FN(HANDLE, dxOpen, void*);
FN(BOOL, dxClose, HANDLE);
FN(HANDLE, dxRegister, HANDLE, void*, GLuint, GLenum, GLenum);
FN(BOOL, dxUnregister, HANDLE, HANDLE);
FN(BOOL, dxLock, HANDLE, GLint, HANDLE*);
FN(BOOL, dxUnlock, HANDLE, GLint, HANDLE*);
FN(void, genFbo, GLsizei, GLuint*);
FN(void, deleteFbo, GLsizei, const GLuint*);
FN(void, bindFbo, GLenum, GLuint);
FN(void, attachTex, GLenum, GLenum, GLenum, GLuint, GLint);
FN(GLenum, checkFbo, GLenum);
FN(void, blitFbo, GLint, GLint, GLint, GLint, GLint, GLint, GLint, GLint, GLbitfield, GLenum);
FN(GLuint, createShader, GLenum);
FN(void, shaderSource, GLuint, GLsizei, const GLchar* const*, const GLint*);
FN(void, compileShader, GLuint);
FN(void, getShaderiv, GLuint, GLenum, GLint*);
FN(void, getShaderLog, GLuint, GLsizei, GLsizei*, GLchar*);
FN(void, deleteShader, GLuint);
FN(GLuint, createProgram);
FN(void, attachShader, GLuint, GLuint);
FN(void, linkProgram, GLuint);
FN(void, getProgramiv, GLuint, GLenum, GLint*);
FN(void, getProgramLog, GLuint, GLsizei, GLsizei*, GLchar*);
FN(void, deleteProgram, GLuint);
FN(void, useProgram, GLuint);
FN(GLint, uniformLocation, GLuint, const GLchar*);
FN(void, uniform1i, GLint, GLint);
FN(void, uniform1f, GLint, GLfloat);
FN(void, uniform2f, GLint, GLfloat, GLfloat);
FN(void, genVao, GLsizei, GLuint*);
FN(void, bindVao, GLuint);
FN(void, deleteVao, GLsizei, const GLuint*);
FN(void, activeTex, GLenum);
FN(void, bindSampler, GLuint, GLuint);
FN(void, memoryBarrier, GLbitfield);

template<typename T> bool load(T& fn, const char* name) {
    fn = reinterpret_cast<T>(wglGetProcAddress(name));
    auto p = reinterpret_cast<intptr_t>(fn);
    if (p == 0 || p == 1 || p == 2 || p == 3 || p == -1) {
        error = std::string("Missing GL extension: ") + name;
        return false;
    }
    return true;
}

bool initializeGL() {
    if (!wglGetCurrentContext()) { error = "No current OpenGL context"; return false; }
    // Resolve against the current application's context, never make another context current.
#define L(name, symbol) if (!load(name, symbol)) return false
    L(dxOpen, "wglDXOpenDeviceNV"); L(dxClose, "wglDXCloseDeviceNV");
    L(dxRegister, "wglDXRegisterObjectNV"); L(dxUnregister, "wglDXUnregisterObjectNV");
    L(dxLock, "wglDXLockObjectsNV"); L(dxUnlock, "wglDXUnlockObjectsNV");
    L(genFbo, "glGenFramebuffers"); L(deleteFbo, "glDeleteFramebuffers");
    L(bindFbo, "glBindFramebuffer"); L(attachTex, "glFramebufferTexture2D");
    L(checkFbo, "glCheckFramebufferStatus"); L(blitFbo, "glBlitFramebuffer");
    L(createShader, "glCreateShader"); L(shaderSource, "glShaderSource");
    L(compileShader, "glCompileShader"); L(getShaderiv, "glGetShaderiv");
    L(getShaderLog, "glGetShaderInfoLog"); L(deleteShader, "glDeleteShader");
    L(createProgram, "glCreateProgram"); L(attachShader, "glAttachShader");
    L(linkProgram, "glLinkProgram"); L(getProgramiv, "glGetProgramiv");
    L(getProgramLog, "glGetProgramInfoLog"); L(deleteProgram, "glDeleteProgram");
    L(useProgram, "glUseProgram"); L(uniformLocation, "glGetUniformLocation");
    L(uniform1i, "glUniform1i"); L(uniform1f, "glUniform1f"); L(uniform2f, "glUniform2f");
    L(genVao, "glGenVertexArrays"); L(bindVao, "glBindVertexArray");
    L(deleteVao, "glDeleteVertexArrays"); L(activeTex, "glActiveTexture");
    L(bindSampler, "glBindSampler");
    L(memoryBarrier,"glMemoryBarrier");
#undef L
    return true;
}

bool failed(const char* operation, HRESULT result = S_OK) {
    char message[256];
    sprintf_s(message, "%s (HRESULT=0x%08lx, Win32=%lu)", operation, result, GetLastError());
    error = message;
    return false;
}

struct Slot { ID3D11Texture2D* dx = nullptr; HANDLE share = nullptr, object = nullptr; GLuint gl = 0, fbo = 0; };
struct Bridge {
    ID3D11Device* device = nullptr;
    ID3D11DeviceContext* dc = nullptr;
    HANDLE interop = nullptr, mutex = nullptr;
    HGLRC context = nullptr;
    Slot slots[2];
    int width = 0, height = 0;
    GLuint program = 0, vao = 0;
    ~Bridge() {
        bool current = context && context == wglGetCurrentContext();
        if (current) {
            for (auto& s : slots) {
                if (s.object) dxUnregister(interop, s.object);
                if (s.fbo) deleteFbo(1, &s.fbo);
                if (s.gl) glDeleteTextures(1, &s.gl);
            }
            if (program) deleteProgram(program);
            if (vao) deleteVao(1, &vao);
            if (interop) dxClose(interop);
        }
        // If the caller has lost its context, keep the interop-owned COM resources
        // alive until process exit rather than releasing a registered resource.
        if (current || !interop) {
            for (auto& s : slots) if (s.dx) s.dx->Release();
            if (dc) dc->Release();
            if (device) device->Release();
        }
        if (mutex) CloseHandle(mutex);
    }
    bool setup(const wchar_t* name, int w, int h, const uint64_t* handles) {
        if (w < 1 || h < 1 || w > 8192 || h > 8192) { error = "Invalid dimensions"; return false; }
        if (!initializeGL()) return false;
        context = wglGetCurrentContext(); width = w; height = h;
        mutex = CreateMutexW(nullptr, FALSE, name);
        if (!mutex) return failed("CreateMutex");
        HRESULT hr = D3D11CreateDevice(nullptr, D3D_DRIVER_TYPE_HARDWARE, nullptr,
            D3D11_CREATE_DEVICE_BGRA_SUPPORT, nullptr, 0, D3D11_SDK_VERSION, &device, nullptr, &dc);
        if (FAILED(hr)) return failed("D3D11CreateDevice", hr);
        interop = dxOpen(device);
        if (!interop) return failed("wglDXOpenDeviceNV");
        for (int i = 0; i < 2; ++i) {
            auto& s = slots[i];
            if (handles) {
                hr = device->OpenSharedResource(reinterpret_cast<HANDLE>(handles[i]), __uuidof(ID3D11Texture2D), reinterpret_cast<void**>(&s.dx));
                s.share = reinterpret_cast<HANDLE>(handles[i]);
            } else {
                D3D11_TEXTURE2D_DESC desc{};
                desc.Width = w; desc.Height = h; desc.MipLevels = desc.ArraySize = 1;
                desc.Format = i == 0 ? DXGI_FORMAT_R16G16B16A16_FLOAT : DXGI_FORMAT_R32_FLOAT;
                desc.SampleDesc.Count = 1; desc.Usage = D3D11_USAGE_DEFAULT;
                desc.BindFlags = D3D11_BIND_RENDER_TARGET | D3D11_BIND_SHADER_RESOURCE;
                desc.MiscFlags = D3D11_RESOURCE_MISC_SHARED;
                hr = device->CreateTexture2D(&desc, nullptr, &s.dx);
                if (SUCCEEDED(hr)) {
                    IDXGIResource* resource = nullptr;
                    hr = s.dx->QueryInterface(__uuidof(IDXGIResource), reinterpret_cast<void**>(&resource));
                    if (SUCCEEDED(hr)) { hr = resource->GetSharedHandle(&s.share); resource->Release(); }
                }
            }
            if (FAILED(hr)) return failed(handles ? "OpenSharedResource" : "Create shared texture", hr);
            glGenTextures(1, &s.gl);
            s.object = dxRegister(interop, s.dx, s.gl, GL_TEXTURE_2D, handles ? 0x0000 : 0x0001);
            if (!s.object) return failed("wglDXRegisterObjectNV");
            genFbo(1, &s.fbo);
        }
        return true;
    }
    bool lock(HANDLE* objects, int n) {
        if (context != wglGetCurrentContext()) { error = "GL context changed"; return false; }
        DWORD result = WaitForSingleObject(mutex, 1000);
        if (result != WAIT_OBJECT_0 && result != WAIT_ABANDONED) return failed("GPU mutex timeout");
        if (!dxLock(interop, n, objects)) { ReleaseMutex(mutex); return failed("wglDXLockObjectsNV"); }
        return true;
    }
    bool unlock(HANDLE* objects, int n) {
        // The other process uses a different D3D device. A CPU mutex alone
        // cannot protect GL work still queued on this device's GPU stream.
        glFinish();
        BOOL result = dxUnlock(interop, n, objects);
        dc->Flush();
        ReleaseMutex(mutex);
        return result ? true : failed("wglDXUnlockObjectsNV");
    }
};

GLuint shader(GLenum type, const char* source) {
    GLuint s = createShader(type); shaderSource(s, 1, &source, nullptr); compileShader(s);
    GLint ok = 0; getShaderiv(s, 0x8B81, &ok);
    if (!ok) { char log[4096]{}; getShaderLog(s, sizeof(log), nullptr, log); error = log; deleteShader(s); return 0; }
    return s;
}

const char* vertex = R"GLSL(#version 330 core
out vec2 imageUV;
void main() {
    imageUV = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);
    gl_Position = vec4(imageUV * 2.0 - 1.0, 0.0, 1.0);
})GLSL";
const char* fragment = R"GLSL(#version 330 core
in vec2 imageUV;
out vec4 outputColor;
uniform sampler2D colorImage, depthImage;
uniform bool bloom, dof, ambientOcclusion, isOrtho;
uniform float threshold, strength, focus, focal, fstop, sensor, nearClip, farClip, focusScale;
uniform float aoRadius, aoAmount, tanHalfFov, orthoWidth;
uniform vec2 cameraShift;
uniform vec2 pixelSize;
vec3 viewPosition(vec2 uv) {
    float d=texture(depthImage,uv).r;
    float z=isOrtho ? mix(nearClip,farClip,d) : nearClip*farClip/max(.00001,farClip-d*(farClip-nearClip));
    vec2 ray=(uv*2.0-1.0+cameraShift*2.0)*vec2(1.0,pixelSize.x/pixelSize.y);
    return vec3(ray*(isOrtho ? orthoWidth*.5 : z*tanHalfFov),-z);
}
float occlusion(vec2 uv,float depth) {
    if(depth>=.999999 || aoRadius<=0.0 || aoAmount<=0.0)return 1.0;
    vec3 p=viewPosition(uv);
    vec3 l=p-viewPosition(uv-vec2(pixelSize.x,0)),r=viewPosition(uv+vec2(pixelSize.x,0))-p;
    vec3 b=p-viewPosition(uv-vec2(0,pixelSize.y)),t=viewPosition(uv+vec2(0,pixelSize.y))-p;
    vec3 n=normalize(cross(abs(l.z)<abs(r.z)?l:r,abs(b.z)<abs(t.z)?b:t));
    if(dot(n,-p)<0.0)n=-n;
    float radius=max(.00001,aoRadius*(isOrtho?orthoWidth:2.0*(-p.z)*tanHalfFov));
    float total=0.0;
    for(int i=0;i<8;++i) {
        float angle=(float(i)+.25)*.7853981634;
        for(int j=1;j<=2;++j) {
            vec2 offset=vec2(cos(angle),sin(angle))*aoRadius*(float(j)*.5)*vec2(1.0,pixelSize.y/pixelSize.x);
            vec2 qUV=uv+offset;
            if(any(lessThan(qUV,vec2(0)))||any(greaterThan(qUV,vec2(1))))continue;
            vec3 delta=viewPosition(qUV)-p;
            float dist=length(delta);
            float horizon=max(0.0,dot(n,delta)/max(dist,.00001)-.08);
            total+=horizon*(1.0-smoothstep(0.0,radius,dist));
        }
    }
    return 1.0-clamp(total*aoAmount/8.0,0.0,.9);
}
void main() {
    vec3 color = texture(colorImage, imageUV).rgb;
    float d = texture(depthImage, imageUV).r;
    if (dof) {
        float z = nearClip * farClip / max(0.00001, farClip - d * (farClip - nearClip));
        z *= focusScale;
        float f = max(0.0001, focus * focusScale);
        float circle = focal / max(fstop, 0.1) * abs(z-f) / max(z, 0.00001) * focal / max(abs(f-focal),focal*.01);
        float radius = min(.125/pixelSize.x, 0.5 * circle / sensor / pixelSize.x);
        vec3 blurred = vec3(0); float total = 0;
        for (int i=0;i<48;++i) {
            float r=sqrt((float(i)+.5)/48.0);
            float angle=float(i)*2.39996323;
            vec2 o=vec2(cos(angle),sin(angle))*r;
            float w=exp(-2.0*r*r);
            blurred += texture(colorImage, imageUV+o*pixelSize*radius).rgb*w; total+=w;
        }
        color=blurred/total;
    }
    if (bloom) {
        vec3 halo=vec3(0); float total=0;
        for (int y=-3;y<=3;++y) for (int x=-3;x<=3;++x) {
            vec2 o=vec2(x,y); float w=exp(-dot(o,o)/4.0);
            halo+=max(texture(colorImage,imageUV+o*pixelSize*4.0).rgb-vec3(threshold),vec3(0))*w; total+=w;
        }
        color+=halo*strength/total;
    }
    if(ambientOcclusion)color*=occlusion(imageUV,d);
    outputColor=vec4(color,1); gl_FragDepth=d;
})GLSL";

struct SavedGLState {
    GLint program, vao, active, textures[2], samplers[2], depthFunc;
    GLboolean depthMask, colorMask[4];
    GLenum flags[7] = {GL_DEPTH_TEST, GL_BLEND, GL_CULL_FACE, GL_SCISSOR_TEST, GL_STENCIL_TEST, 0x8DB9, GL_DITHER};
    bool enabled[7];
    bool clips[8];
    SavedGLState() {
        glGetIntegerv(0x8B8D,&program); glGetIntegerv(0x85B5,&vao); glGetIntegerv(0x84E0,&active);
        for(int i=0;i<2;++i) { activeTex(0x84C0+i); glGetIntegerv(GL_TEXTURE_BINDING_2D,&textures[i]); glGetIntegerv(0x8919,&samplers[i]); }
        glGetIntegerv(GL_DEPTH_FUNC,&depthFunc); glGetBooleanv(GL_DEPTH_WRITEMASK,&depthMask); glGetBooleanv(GL_COLOR_WRITEMASK,colorMask);
        for(int i=0;i<7;++i) enabled[i]=glIsEnabled(flags[i]) != 0;
        for(int i=0;i<8;++i) clips[i]=glIsEnabled(0x3000+i)!=0;
    }
    ~SavedGLState() {
        for(int i=0;i<7;++i) { if(enabled[i]) glEnable(flags[i]); else glDisable(flags[i]); }
        for(int i=0;i<8;++i) { if(clips[i]) glEnable(0x3000+i); else glDisable(0x3000+i); }
        glDepthFunc(depthFunc); glDepthMask(depthMask); glColorMask(colorMask[0],colorMask[1],colorMask[2],colorMask[3]);
        for(int i=0;i<2;++i) { activeTex(0x84C0+i); glBindTexture(GL_TEXTURE_2D,textures[i]); bindSampler(i,samplers[i]); }
        activeTex(active); bindVao(vao); useProgram(program);
    }
};
thread_local unsigned lastClipMask=0;
}

API const char* eb_error() { return error.c_str(); }
API unsigned eb_clip_mask() { return lastClipMask; }
API uint64_t eb_context() { return reinterpret_cast<uint64_t>(wglGetCurrentContext()); }
API void* eb_create(const wchar_t* name, int width, int height, const uint64_t* handles) {
    error.clear(); auto b = new Bridge;
    if (!b->setup(name,width,height,handles)) { delete b; return nullptr; }
    return b;
}
API uint64_t eb_handle(void* ptr, int channel) {
    return ptr && channel>=0 && channel<2 ? reinterpret_cast<uint64_t>(static_cast<Bridge*>(ptr)->slots[channel].share) : 0;
}
API void eb_destroy(void* ptr) { delete static_cast<Bridge*>(ptr); }
API int eb_publish(void* ptr, int channel) {
    if (!ptr || channel<0 || channel>1) return 0;
    auto b=static_cast<Bridge*>(ptr); auto& s=b->slots[channel];
    if (!b->lock(&s.object,1)) return 0;
    // Eevee can finish its film with shader image writes. Make those visible
    // to this direct framebuffer blit, outside Blender's GPU state manager.
    memoryBarrier(0x00000400u | 0x00000100u | 0x00000020u | 0x00000008u);
    GLint read=0,draw=0; glGetIntegerv(0x8CAA,&read); glGetIntegerv(0x8CA6,&draw);
    bool scissor=glIsEnabled(GL_SCISSOR_TEST)!=0; glDisable(GL_SCISSOR_TEST);
    bindFbo(0x8CA9,s.fbo); attachTex(0x8CA9,0x8CE0,GL_TEXTURE_2D,s.gl,0);
    bool complete=checkFbo(0x8CA9)==0x8CD5;
    if (complete) blitFbo(0,0,b->width,b->height,0,0,b->width,b->height,GL_COLOR_BUFFER_BIT,GL_NEAREST);
    bindFbo(0x8CA8,read); bindFbo(0x8CA9,draw);
    if(scissor) glEnable(GL_SCISSOR_TEST);
    bool unlocked=b->unlock(&s.object,1);
    if(!complete) error="Shared framebuffer is incomplete";
    return complete && unlocked;
}
// values: bloom..focusScale (11), AO enabled/radius/amount, tanFov,
// orthographic/width, camera shift X/Y (19 total).
API int eb_draw(void* ptr, const float* values) {
    if(!ptr || !values) return 0;
    auto b=static_cast<Bridge*>(ptr);
    if(b->context!=wglGetCurrentContext()) { error="No matching Maya GL context"; return 0; }
    SavedGLState saved;
    lastClipMask=0;
    for(int i=0;i<8;++i) {
        if(saved.clips[i])lastClipMask|=1u<<i;
        // Maya's spotlight/manipulator passes can leave user clipping active.
        // This fullscreen shader has no gl_ClipDistance outputs.
        glDisable(0x3000+i);
    }
    if(!b->program) {
        GLuint vs=shader(0x8B31,vertex), fs=shader(0x8B30,fragment);
        if(!vs || !fs) { if(vs) deleteShader(vs); if(fs) deleteShader(fs); return 0; }
        b->program=createProgram(); attachShader(b->program,vs); attachShader(b->program,fs); linkProgram(b->program);
        deleteShader(vs); deleteShader(fs); GLint ok=0; getProgramiv(b->program,0x8B82,&ok);
        if(!ok) { char log[4096]{}; getProgramLog(b->program,sizeof(log),nullptr,log); error=log; deleteProgram(b->program); b->program=0; return 0; }
        genVao(1,&b->vao);
    }
    HANDLE objects[2]={b->slots[0].object,b->slots[1].object};
    if(!b->lock(objects,2)) return 0;
    for(int i=1;i<7;++i) glDisable(saved.flags[i]);
    glEnable(GL_DEPTH_TEST); glDepthFunc(GL_ALWAYS); glDepthMask(GL_TRUE); glColorMask(GL_TRUE,GL_TRUE,GL_TRUE,GL_TRUE);
    useProgram(b->program); bindVao(b->vao);
    for(int i=0;i<2;++i) { activeTex(0x84C0+i); glBindTexture(GL_TEXTURE_2D,b->slots[i].gl); bindSampler(i,0);
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR); glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,0x812F); glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,0x812F); }
    uniform1i(uniformLocation(b->program,"colorImage"),0); uniform1i(uniformLocation(b->program,"depthImage"),1);
    uniform1i(uniformLocation(b->program,"bloom"),values[0]!=0); uniform1i(uniformLocation(b->program,"dof"),values[3]!=0);
    const char* names[8]={"threshold","strength","focus","focal","fstop","sensor","nearClip","farClip"};
    const int indices[8]={1,2,4,5,6,7,8,9};
    for(int i=0;i<8;++i) uniform1f(uniformLocation(b->program,names[i]),values[indices[i]]);
    uniform1f(uniformLocation(b->program,"focusScale"),values[10]);
    uniform1i(uniformLocation(b->program,"ambientOcclusion"),values[11]!=0);
    uniform1f(uniformLocation(b->program,"aoRadius"),values[12]);
    uniform1f(uniformLocation(b->program,"aoAmount"),values[13]);
    uniform1f(uniformLocation(b->program,"tanHalfFov"),values[14]);
    uniform1i(uniformLocation(b->program,"isOrtho"),values[15]!=0);
    uniform1f(uniformLocation(b->program,"orthoWidth"),values[16]);
    uniform2f(uniformLocation(b->program,"cameraShift"),values[17],values[18]);
    uniform2f(uniformLocation(b->program,"pixelSize"),1.f/b->width,1.f/b->height);
    glDrawArrays(GL_TRIANGLES,0,3);
    return b->unlock(objects,2);
}
