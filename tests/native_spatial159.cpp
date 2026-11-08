#include "line_spatial159.h"
#include <cassert>
#include <iostream>
#include <numeric>
#include <random>

int main(){
    std::vector<std::array<double,3>> centers;
    for(int z=0;z<16;++z)for(int y=0;y<16;++y)for(int x=0;x<16;++x)centers.push_back({double(x),double(y),double(z)});
    std::mt19937 random(159);std::shuffle(centers.begin(),centers.end(),random);
    auto order=lineSpatial159::stableMortonOrder(centers.size(),[&](size_t i){return centers[i];});
    auto sorted=order;std::sort(sorted.begin(),sorted.end());
    for(size_t i=0;i<sorted.size();++i)assert(sorted[i]==i);
    // A compact block in Morton order contains a small spatial neighborhood.
    for(size_t first=0;first<order.size();first+=64){
        std::array<double,3> low{{100,100,100}},high{{-100,-100,-100}};
        for(size_t i=first;i<first+64;++i)for(int k=0;k<3;++k){low[k]=std::min(low[k],centers[order[i]][k]);high[k]=std::max(high[k],centers[order[i]][k]);}
        for(int k=0;k<3;++k)assert(high[k]-low[k]<=3.);
    }
    auto equal=lineSpatial159::stableMortonOrder(200,[&](size_t){return std::array<double,3>{{7,7,7}};});
    for(size_t i=0;i<equal.size();++i)assert(equal[i]==i);
    assert(lineSpatial159::stableMortonOrder(0,[&](size_t){return centers[0];}).empty());
    double identity[16]={1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1};
    double low[3]={-.1,-.1,-1},high[3]={.1,.1,1};
    assert(lineSpatial159::boundsVisible(low,high,identity,1000,700,2));
    low[0]=high[0]=1.003;assert(lineSpatial159::boundsVisible(low,high,identity,1000,700,2));
    low[0]=2;high[0]=3;assert(!lineSpatial159::boundsVisible(low,high,identity,1000,700,2));
    low[0]=std::numeric_limits<double>::quiet_NaN();assert(lineSpatial159::boundsVisible(low,high,identity,1000,700,2));
    double projection[16]={1.3,0,0,0,0,1.7,0,0,0,0,-1,-1,0,0,-.1,0};
    std::uniform_real_distribution<double> position(-1e6,1e6),screen(-1,1),distance(10,1e5);
    for(int attempt=0;attempt<10000;++attempt){
        double eye[3]={position(random),position(random),position(random)},vp[16];std::copy(projection,projection+16,vp);
        for(int c=0;c<4;++c)vp[12+c]-=eye[0]*projection[c]+eye[1]*projection[4+c]+eye[2]*projection[8+c];
        double depth=distance(random);double point[3]={eye[0]+screen(random)*depth/1.3,eye[1]+screen(random)*depth/1.7,eye[2]-depth};
        for(int k=0;k<3;++k){low[k]=point[k]-.01;high[k]=point[k]+.01;}
        assert(lineSpatial159::boundsVisible(low,high,vp,1453,797,2));
        // A box fully behind the camera can never emit a visible segment.
        low[0]=high[0]=eye[0];low[1]=high[1]=eye[1];low[2]=eye[2]+100;high[2]=eye[2]+101;
        assert(!lineSpatial159::boundsVisible(low,high,vp,1453,797,2));
    }
    std::cout<<"PASS: stable spatial permutation/locality; unchanged tie ordering; conservative border/large-origin/perspective bounds (10000 views).\n";
}
