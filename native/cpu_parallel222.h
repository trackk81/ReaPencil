#pragma once
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <atomic>
#include <exception>
#include <vector>

namespace rp222 {
// Reuse the Windows worker pool. Creating thousands of short-lived threads
// repeatedly initializes every loaded Maya plug-in's thread-local state.
// All callbacks finish before their stack context or this DLL can be released.
template<class Function> void parallel(unsigned workers,Function&& function){
 if(workers<=1){function(0);return;}
 struct Work {
  Function& function;std::atomic<unsigned> next{1};
  std::vector<std::exception_ptr> errors;
  Work(Function& f,unsigned n):function(f),errors(n){}
  static void CALLBACK callback(PTP_CALLBACK_INSTANCE,void* context,PTP_WORK){
   auto& work=*static_cast<Work*>(context);unsigned i=work.next.fetch_add(1);
   try{work.function(i);}catch(...){work.errors[i]=std::current_exception();}
  }
 } state(function,workers);
 PTP_WORK work=CreateThreadpoolWork(Work::callback,&state,nullptr);
 if(!work){for(unsigned i=0;i<workers;++i)function(i);return;}
 for(unsigned i=1;i<workers;++i)SubmitThreadpoolWork(work);
 try{function(0);}catch(...){state.errors[0]=std::current_exception();}
 WaitForThreadpoolWorkCallbacks(work,FALSE);CloseThreadpoolWork(work);
 for(auto& error:state.errors)if(error)std::rethrow_exception(error);
}
}
