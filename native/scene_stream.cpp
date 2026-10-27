// Evaluate output meshes in Maya. Painted skin weights/deformer order remain owned by Maya.
#include <maya/MDagPath.h>
#include <maya/MSelectionList.h>
#include <maya/MFnMesh.h>
#include <maya/MObjectHandle.h>
#include <maya/MMatrix.h>
#include <maya/MIntArray.h>
#include <maya/MStatus.h>
#include <maya/MPlug.h>
#include <maya/MNodeMessage.h>
#include <maya/MMessage.h>
#include <vector>
#include <string>
#include <cstdint>
#include <cstring>

#define API extern "C" __declspec(dllexport)
namespace {
thread_local std::string error;
struct Mesh {
    MDagPath path;
    MObjectHandle handle;
    std::vector<float> points, normals;
    MIntArray normalIds;
    int vertices=0, faces=0, loops=0;
    MMatrix matrix;
    bool visible=true;
    bool smooth=false;
    bool dirty=true;
    MCallbackId callback=0;
};
struct Cache {
    std::vector<Mesh> meshes;
    std::vector<char> packet;
    uint32_t evaluations=0;
    ~Cache() {
        for(auto& mesh:meshes) if(mesh.callback) MMessage::removeCallback(mesh.callback);
    }
    template<typename T> void append(const T* value, size_t count) {
        const char* p=reinterpret_cast<const char*>(value);
        packet.insert(packet.end(),p,p+sizeof(T)*count);
    }
    void integer(uint32_t v) { append(&v,1); }
    bool update(bool initial) {
        packet.clear(); integer(0); uint32_t changes=0; evaluations=0;
        for(uint32_t index=0;index<meshes.size();++index) {
            auto& mesh=meshes[index];
            if(!mesh.handle.isValid() || !mesh.handle.isAlive()) { error="Mesh deleted; rebuild cache"; return false; }
            bool visible=mesh.path.isVisible();
            if(!initial && !visible) {
                // Hidden rigs and alternate geometry need no point/normal or
                // subdivision evaluation. Read the current output on reveal.
                if(mesh.visible) {
                    ++changes; integer(index); integer(16); integer(mesh.vertices); integer(0); integer(0);
                    mesh.visible=false;
                }
                continue;
            }
            MMatrix matrix=mesh.path.inclusiveMatrix();
            if(!initial && !mesh.dirty && mesh.visible) {
                if(matrix!=mesh.matrix) {
                    ++changes; integer(index); integer(1); integer(mesh.vertices); integer(0); integer(1);
                    append(&matrix.matrix[0][0],16); mesh.matrix=matrix;
                }
                continue;
            }
            ++evaluations;
            MStatus status; MFnMesh fn(mesh.path,&status);
            if(!status) { error=status.errorString().asChar(); return false; }
            bool smooth=visible && fn.findPlug("displaySmoothMesh",false,&status).asInt()!=0;
            if(!status) { error="Cannot read Smooth Mesh Preview"; return false; }
            if(!initial && smooth!=mesh.smooth) {
                error="Smooth Mesh Preview changed; rebuild cache"; return false;
            }
            // outSmoothMesh is Maya's evaluated preview: it preserves the native
            // subdivision algorithm, creases, UV rules and deformer results.
            // Keep its data object alive until all raw pointers have been copied.
            MObject preview;
            if(smooth) {
                preview=fn.findPlug("outSmoothMesh",false,&status).asMObject();
                if(status) status=fn.setObject(preview);
                if(!status) { error="Cannot evaluate Smooth Mesh Preview"; return false; }
            }
            int vertices=fn.numVertices(), faces=fn.numPolygons(), loops=fn.numFaceVertices();
            if(!initial && (vertices!=mesh.vertices || faces!=mesh.faces || loops!=mesh.loops)) {
                error="Topology changed; rebuild cache"; return false;
            }
            const float* points=fn.getRawPoints(&status);
            if(!status || (!points && vertices)) { error="Cannot evaluate mesh points"; return false; }
            uint32_t flags=0;
            if(initial || matrix!=mesh.matrix) flags|=1;
            if(initial || !mesh.visible || mesh.points.size()!=size_t(vertices*3) ||
               std::memcmp(mesh.points.data(),points,vertices*3*sizeof(float))) flags|=2;
            if(initial || visible!=mesh.visible) flags|=16;
            // Normals are fetched only when geometry changes; transforms preserve object normals.
            std::vector<float> normals;
            if(flags&2) {
                MIntArray counts; fn.getNormalIds(counts,mesh.normalIds);
                const float* raw=fn.getRawNormals(&status);
                if(status && raw && mesh.normalIds.length()==unsigned(loops)) {
                    normals.resize(loops*3);
                    for(int i=0;i<loops;++i) std::memcpy(normals.data()+i*3,raw+mesh.normalIds[i]*3,3*sizeof(float));
                    if(initial || normals!=mesh.normals) flags|=4;
                }
            }
            mesh.vertices=vertices; mesh.faces=faces; mesh.loops=loops; mesh.smooth=smooth;
            mesh.dirty=false;
            if(!flags) continue;
            ++changes;
            integer(index); integer(flags); integer(vertices); integer((flags&4)?loops:0); integer(visible?1:0);
            if(flags&1) { append(&matrix.matrix[0][0],16); mesh.matrix=matrix; }
            if(flags&2) { append(points,vertices*3); mesh.points.assign(points,points+vertices*3); }
            if(flags&4) { append(normals.data(),normals.size()); mesh.normals=std::move(normals); }
            mesh.visible=visible;
        }
        std::memcpy(packet.data(),&changes,4);
        return true;
    }
};
}
API const char* es_error() { return error.c_str(); }
API void* es_create(const char* const* names, uint32_t count) {
    auto cache=new Cache;
    cache->meshes.reserve(count);
    for(uint32_t i=0;i<count;++i) {
        MSelectionList selection; MDagPath path;
        MStatus status=selection.add(names[i]);
        if(status) status=selection.getDagPath(0,path);
        if(!status) { error=status.errorString().asChar(); delete cache; return nullptr; }
        Mesh mesh; mesh.path=path; mesh.handle=MObjectHandle(path.node());
        cache->meshes.push_back(std::move(mesh));
    }
    for(auto& mesh:cache->meshes) {
        MStatus status; MFnMesh fn(mesh.path,&status);
        if(!status) { error="Cannot watch evaluated mesh"; delete cache; return nullptr; }
        mesh.callback=MNodeMessage::addNodeDirtyCallback(mesh.path.node(),
            [](MObject&, void* data) { static_cast<Mesh*>(data)->dirty=true; }, &mesh, &status);
        if(!status) { error="Cannot watch mesh dirtiness"; delete cache; return nullptr; }
    }
    return cache;
}
API const void* es_update(void* ptr, int initial, uint64_t* length) {
    if(!ptr || !length) return nullptr;
    auto cache=static_cast<Cache*>(ptr);
    if(!cache->update(initial!=0)) return nullptr;
    *length=cache->packet.size(); return cache->packet.data();
}
API void es_destroy(void* ptr) { delete static_cast<Cache*>(ptr); }
API uint32_t es_evaluations(void* ptr) { return ptr?static_cast<Cache*>(ptr)->evaluations:0; }
