#pragma once
// Camera-independent spatial ordering and conservative camera-only bounds tests.
// No Maya API, persistent membership never changes on a camera movement.
#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <vector>

namespace lineSpatial159 {
inline uint32_t spread10(uint32_t value) {
    value&=1023u;value=(value|(value<<16))&0x030000ffu;
    value=(value|(value<<8))&0x0300f00fu;
    value=(value|(value<<4))&0x030c30c3u;
    return (value|(value<<2))&0x09249249u;
}

// center(index) -> std::array<double,3>. Equal Morton cells retain input order.
// Three stable 10-bit radix passes avoid per-camera or comparison-sort work.
template<class Center>
std::vector<size_t> stableMortonOrder(size_t count,Center center) {
    if(!count)return {};
    std::array<double,3> low{{INFINITY,INFINITY,INFINITY}},high{{-INFINITY,-INFINITY,-INFINITY}};
    for(size_t i=0;i<count;++i){auto p=center(i);for(int k=0;k<3;++k)if(std::isfinite(p[k])){
        low[k]=std::min(low[k],p[k]);high[k]=std::max(high[k],p[k]);}}
    struct Entry {uint32_t key;size_t index;};
    std::vector<Entry> entries(count),scratch(count);
    for(size_t i=0;i<count;++i){auto p=center(i);uint32_t q[3];
        for(int k=0;k<3;++k){
            double scaled=(high[k]>low[k]&&std::isfinite(p[k]))?(p[k]-low[k])*(1023.0/(high[k]-low[k])):0.;
            q[k]=uint32_t(std::max(0.,std::min(1023.,scaled)));
        }
        entries[i]={spread10(q[0])|(spread10(q[1])<<1)|(spread10(q[2])<<2),i};
    }
    for(unsigned shift=0;shift<30;shift+=10){
        std::array<size_t,1024> offsets{};
        for(const auto& entry:entries)++offsets[(entry.key>>shift)&1023u];
        size_t total=0;for(auto& n:offsets){size_t size=n;n=total;total+=size;}
        for(const auto& entry:entries)scratch[offsets[(entry.key>>shift)&1023u]++]=entry;
        entries.swap(scratch);
    }
    std::vector<size_t> result(count);for(size_t i=0;i<count;++i)result[i]=entries[i].index;
    return result;
}

// MFrameContext row-vector VP matrix. Only x/y/w planes are needed to reject
// offscreen chunks; omitting near/far rejection is conservative for every depth
// convention. Stroke extrusion and float shader arithmetic get explicit guards.
inline bool boundsVisible(const double low[3],const double high[3],const double vp[16],
                          unsigned width,unsigned height,double lineWidth) {
    if(!width||!height)return true;
    for(int k=0;k<3;++k)if(!std::isfinite(low[k])||!std::isfinite(high[k])||low[k]>high[k])return true;
    const double mx=1.+(std::max(0.,lineWidth)+4.)/double(width);
    const double my=1.+(std::max(0.,lineWidth)+4.)/double(height);
    std::array<std::array<double,4>,5> planes;
    for(int r=0;r<4;++r){
        planes[0][r]=vp[r*4+3]*mx+vp[r*4];planes[1][r]=vp[r*4+3]*mx-vp[r*4];
        planes[2][r]=vp[r*4+3]*my+vp[r*4+1];planes[3][r]=vp[r*4+3]*my-vp[r*4+1];
        planes[4][r]=vp[r*4+3];
    }
    for(const auto& plane:planes){
        double maximum=plane[3],magnitude=std::abs(plane[3])+1.;
        for(int k=0;k<3;++k){
            maximum+=plane[k]*(plane[k]>=0?high[k]:low[k]);
            magnitude+=std::abs(plane[k])*std::max(std::abs(low[k]),std::abs(high[k]));
        }
        double guard=magnitude*(16.*std::numeric_limits<float>::epsilon());
        if(maximum < -guard)return false;
    }
    return true;
}
} // namespace lineSpatial159
