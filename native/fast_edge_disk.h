// Numeric, bounded, checksummed viewport cache. Never contains executable code.
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <Windows.h>
#include <filesystem>
#include <fstream>
#include <cstring>
#include <limits>
namespace edgeDisk {
inline unsigned hits=0,misses=0,writes=0;
inline unsigned long long hash(const std::string& s){unsigned long long h=1469598103934665603ull;for(unsigned char c:s)h=(h^c)*1099511628211ull;return h;}
inline std::filesystem::path folder(){
 wchar_t value[32768];DWORD n=GetEnvironmentVariableW(L"REAPENCIL_SMOOTH_CACHE_DIR",value,32768);if(n&&n<32768)return std::filesystem::path(value);
 n=GetEnvironmentVariableW(L"LOCALAPPDATA",value,32768);if(!n||n>=32768)return {};
 return std::filesystem::path(value)/L"ReaPencil"/L"cache"/L"smooth146";
}
inline std::filesystem::path path(const std::string& key){auto root=folder();if(root.empty())return {};return root/(std::to_string(hash(key))+".bin");}
template<class T>void put(std::string& out,const T& value){out.append(reinterpret_cast<const char*>(&value),sizeof(value));}
template<class T>bool get(const std::string& in,size_t& offset,T& value){if(offset>in.size()||sizeof(value)>in.size()-offset)return false;std::memcpy(&value,in.data()+offset,sizeof(value));offset+=sizeof(value);return true;}
inline bool read(const std::string& key,std::string& payload){try{auto p=path(key);if(p.empty()||!std::filesystem::is_regular_file(p)||std::filesystem::file_size(p)>32*1024*1024){++misses;return false;}std::ifstream in(p,std::ios::binary);std::string data((std::istreambuf_iterator<char>(in)),{});size_t offset=0;unsigned magic=0,keySize=0;unsigned long long checksum=0;if(!get(data,offset,magic)||magic!=0x146CA503||!get(data,offset,keySize)||keySize!=key.size()||keySize>8*1024*1024||data.size()-offset<keySize||data.compare(offset,keySize,key)!=0)return false;offset+=keySize;if(!get(data,offset,checksum))return false;payload=data.substr(offset);if(hash(payload)!=checksum)return false;return true;}catch(...){return false;}}
inline void write(const std::string& key,const std::string& payload){try{auto p=path(key);if(p.empty()||payload.size()+key.size()>32*1024*1024)return;std::filesystem::create_directories(p.parent_path());std::string data;unsigned magic=0x146CA503,size=unsigned(key.size());put(data,magic);put(data,size);data+=key;put(data,hash(payload));data+=payload;auto temporary=p;temporary+=L".tmp."+std::to_wstring(GetCurrentProcessId());{std::ofstream out(temporary,std::ios::binary|std::ios::trunc);out.write(data.data(),data.size());out.flush();if(!out)return;}if(MoveFileExW(temporary.c_str(),p.c_str(),MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH))++writes;else std::filesystem::remove(temporary);}catch(...){}}
}
