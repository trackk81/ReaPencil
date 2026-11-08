"""Conservative camera-independent stroke isolation for normal preview."""
import numpy as np

def independent_edges(vertices,features,outline,trace_vertices=False):
    """Prove edges cannot link under the CPU feature-key/valence contract.

    Intersections without mesh vertex identities always remain separate strokes.
    With static feature keys, only valence two can connect. Dynamic silhouettes
    may change that valence, so they retain the exact native tracer.
    """
    result=np.any(vertices<0,axis=1)
    trace=vertices.copy() if trace_vertices else None
    if not outline and len(vertices):
        valid=~result
        if np.any(valid):
            keys=np.c_[np.repeat(features[valid],2),vertices[valid].reshape(-1)]
            _,inverse,counts=np.unique(keys,axis=0,return_inverse=True,return_counts=True)
            blocked=counts[inverse].reshape(-1,2)!=2
            result[valid]=np.all(blocked,axis=1)
            if trace_vertices:
                # Removing GPU-only edges must not turn a branch into a join.
                # Unique endpoint IDs preserve the full graph's non-two valence.
                unique=vertices.max(initial=-1)+1+np.arange(int(valid.sum())*2).reshape(-1,2)
                trace[valid]=np.where(blocked,unique,vertices[valid])
    return (result,trace) if trace_vertices else result
