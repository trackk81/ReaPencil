"""Independent editable brush graph; seven-value runtime rows stay unchanged."""
import copy,math
import numpy as np
from PySide6 import QtCore,QtGui,QtWidgets
from .brush_profiles import validate_profile,evaluate_profile

class CurveCanvas(QtWidgets.QWidget):
    changed=QtCore.Signal()
    selectionChanged=QtCore.Signal()
    _clipboard=None
    def __init__(self,points=(),parent=None):
        super().__init__(parent);self.setObjectName('curve_canvas');self.setMinimumSize(360,185);self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.points=validate_profile(list(points));self.selected=set();self.undo_stack=[];self.redo_stack=[];self.drag=None;self.box=None
    def plot_rect(self):return QtCore.QRectF(38,16,max(1,self.width()-56),max(1,self.height()-43))
    def point_to_pixel(self,x,y):
        r=self.plot_rect();return QtCore.QPointF(r.left()+x*r.width(),r.bottom()-y*r.height())
    def pixel_to_point(self,p):
        r=self.plot_rect();return ((p.x()-r.left())/r.width(),(r.bottom()-p.y())/r.height())
    def _remember(self):self.undo_stack.append(copy.deepcopy(self.points));self.undo_stack=self.undo_stack[-64:];self.redo_stack=[]
    def set_points(self,points,remember=True):
        rows=validate_profile(points)
        if remember:self._remember()
        self.points=rows;self.selected=set();self._notify()
    def _notify(self):self.update();self.changed.emit();self.selectionChanged.emit()
    def _materialize(self):
        if not self.points:self.points=[[0,0,1,0,1,0,1],[0,1,1,1,1,1,1]]
    def _auto(self):
        for i,row in enumerate(self.points):
            if row[0]!=1:continue
            x,y=row[3:5]
            if i==0 or i==len(self.points)-1:row[1:3]=[x,y];row[5:7]=[x,y];continue
            left,right=self.points[i-1],self.points[i+1];slope=(right[4]-left[4])/(right[3]-left[3])
            a=(x-left[3])*.5;b=(right[3]-x)*.5;row[1:3]=[x-a,y-a*slope];row[5:7]=[x+b,y+b*slope]
    @staticmethod
    def editor_value(rows,x):
        """Nine-point UI sampling for new-point/tangent seeding only.

        Rendering and the displayed curve retain the existing adaptive evaluator.
        This matches the original editor's eight-interval interaction contract.
        """
        if not rows:return 1.,0.
        if len(rows)==1:return rows[0][4],0.
        left,right=rows[-2:]
        for a,b in zip(rows,rows[1:]):
            if x<=b[3]:left,right=a,b;break
        a=np.array(left[3:5]);d=np.array(right[3:5])
        if left[0]==right[0]==0:
            y=float(np.interp(x,[a[0],d[0]],[a[1],d[1]]));return y,math.atan2(d[1]-a[1],d[0]-a[0])
        def control(row,other,out):
            cp=np.array(row[3:5]);h=np.array(row[5:7] if out else row[1:3])
            if row[0]==0:return cp
            dx=h[0]-cp[0]
            if (out and dx<=0) or (not out and dx>=0):return np.array([cp[0],h[1]])
            bound=other[3];hx=min(max(h[0],min(cp[0],bound)),max(cp[0],bound))
            return np.array([hx,cp[1]+(h[1]-cp[1])*(hx-cp[0])/dx])
        b=control(left,right,True);c=control(right,left,False);t=np.linspace(0,1,9)[:,None]
        samples=(1-t)**3*a+3*(1-t)**2*t*b+3*(1-t)*t*t*c+t**3*d
        tangent=3*(1-t)**2*(b-a)+6*(1-t)*t*(c-b)+3*t*t*(d-c)
        angles=np.arctan2(tangent[:,1],tangent[:,0]);return float(np.interp(x,samples[:,0],samples[:,1])),float(np.interp(x,samples[:,0],angles))
    def add_point(self,x=None,y=None):
        if len(self.points)>=256:return
        if x is None:
            positions=sorted({0.,1.}|{r[3] for r in self.points});a,b=max(zip(positions,positions[1:]),key=lambda q:q[1]-q[0]);x=(a+b)/2
        x=min(1.,max(0.,float(x)))
        if any(abs(x-r[3])<1e-6 for r in self.points):return
        initial,theta=self.editor_value(self.points,x);y=initial if y is None else min(1.,max(0.,float(y)))
        self._remember();self._materialize()
        if any(abs(x-r[3])<1e-6 for r in self.points):
            self.selected={next(i for i,r in enumerate(self.points) if abs(r[3]-x)<1e-6)};self._notify();return
        left=max([r[3] for r in self.points if r[3]<x],default=0.);right=min([r[3] for r in self.points if r[3]>x],default=1.)
        dx=.1*math.cos(theta);dy=.1*math.sin(theta);self.points.append([2,x-dx,y-dy,x,y,x+dx,y+dy]);self.points.sort(key=lambda r:r[3]);self.selected={next(i for i,r in enumerate(self.points) if r[3]==x)};self._auto();self._notify()
    def remove_selected(self):
        if not self.selected:return
        self._remember();self.points=[r for i,r in enumerate(self.points) if i not in self.selected];self.selected=set();self._auto();self._notify()
    def set_kind(self,kind):
        if not self.selected:return
        before=copy.deepcopy(self.points);self._remember()
        def value(x):return self.editor_value(before,x)[0]
        def angle(x):return self.editor_value(before,x)[1]
        for i in self.selected:
            row=self.points[i];old=int(row[0]);x,y=row[3:5]
            if old==kind:continue
            if kind==2:
                if i==0 or i==len(self.points)-1:
                    if old in (0,1):
                        neighbor=before[i+1] if i==0 else before[i-1];hx=x+.294*(neighbor[3]-x);hy=value(hx)
                        if i==0:row[5:7]=[hx,hy]
                        else:row[1:3]=[hx,hy]
                    if i==0:row[1:3]=[2*x-row[5],2*y-row[6]]
                    else:row[5:7]=[2*x-row[1],2*y-row[2]]
                elif old==3:row[5:7]=[2*x-row[1],2*y-row[2]]
                elif old==1:
                    dx=(row[5]-row[1])*.5;dy=(row[6]-row[2])*.5;row[1:3]=[x-dx,y-dy];row[5:7]=[x+dx,y+dy]
                else:
                    theta=(angle(x-.001)+angle(x+.001))*.5;dx=.1*math.cos(theta);dy=.1*math.sin(theta);row[1:3]=[x-dx,y-dy];row[5:7]=[x+dx,y+dy]
            elif kind==3 and old in (0,1):
                if i==0 or i==len(self.points)-1:
                    neighbor=before[i+1] if i==0 else before[i-1];hx=x+.294*(neighbor[3]-x);hy=value(hx)
                    if i==0:row[1:3]=[x-.1,y];row[5:7]=[hx,hy]
                    else:row[1:3]=[hx,hy];row[5:7]=[x+.1,y]
                elif old==0:
                    left=angle(x-.001);right=angle(x+.001);row[1:3]=[x-.1*math.cos(left),y-.1*math.sin(left)];row[5:7]=[x+.1*math.cos(right),y+.1*math.sin(right)]
            row[0]=int(kind)
        self._auto();self._notify()
    @staticmethod
    def mirror(row):return [row[0],1-row[5],row[6],1-row[3],row[4],1-row[1],row[2]]
    def reverse(self):
        self._remember();old=set(self.selected);n=len(self.points);self.points=sorted([self.mirror(r) for r in self.points],key=lambda r:r[3]);self.selected={n-1-i for i in old};self._notify()
    def symmetry(self):
        sides={self.points[i][3]<.5 for i in self.selected if self.points[i][3]!=.5}
        if len(sides)!=1:return
        left=next(iter(sides));self._remember();kept=[copy.deepcopy(r) for r in self.points if r[3]==.5 or (r[3]<.5)==left];out=[]
        for row in kept:
            if row[3]==.5:
                if row[0]==2:row[0]=3
                if row[0] in (2,3):
                    if left:row[5:7]=[1-row[1],row[2]]
                    else:row[1:3]=[1-row[5],row[6]]
                out.append(row)
            else:out.extend([row,self.mirror(row)])
        self.points=validate_profile(out);self.selected=set();self._auto();self._notify()
    def copy_curve(self):CurveCanvas._clipboard=copy.deepcopy(self.points)
    def paste_curve(self):
        if CurveCanvas._clipboard is not None:self.set_points(copy.deepcopy(CurveCanvas._clipboard))
    def undo(self):
        if self.undo_stack:self.redo_stack.append(copy.deepcopy(self.points));self.points=self.undo_stack.pop();self.selected=set();self._notify()
    def redo(self):
        if self.redo_stack:self.undo_stack.append(copy.deepcopy(self.points));self.points=self.redo_stack.pop();self.selected=set();self._notify()
    def move_selected(self,x=None,y=None,remember=True):
        if not self.selected:return
        anchor=self.points[min(self.selected)];dx=0 if x is None else float(x)-anchor[3];dy=0 if y is None else float(y)-anchor[4]
        dx=max(-min(self.points[i][3] for i in self.selected),min(dx,1-max(self.points[i][3] for i in self.selected)))
        dy=max(-min(self.points[i][4] for i in self.selected),min(dy,1-max(self.points[i][4] for i in self.selected)))
        for i in self.selected:
            if i and i-1 not in self.selected:dx=max(dx,self.points[i-1][3]+1e-6-self.points[i][3])
            if i+1<len(self.points) and i+1 not in self.selected:dx=min(dx,self.points[i+1][3]-1e-6-self.points[i][3])
        if remember:self._remember()
        for i in self.selected:
            r=self.points[i]
            for a,b in ((1,2),(3,4),(5,6)):r[a]+=dx;r[b]+=dy
        self._auto();self._notify()
    def paintEvent(self,event):
        p=QtGui.QPainter(self);p.setRenderHint(QtGui.QPainter.Antialiasing);p.fillRect(self.rect(),QtGui.QColor('#292929'));r=self.plot_rect()
        p.setPen(QtGui.QPen(QtGui.QColor('#474747'),1))
        for i in range(5):
            t=i/4;p.drawLine(self.point_to_pixel(t,0),self.point_to_pixel(t,1));p.drawLine(self.point_to_pixel(0,t),self.point_to_pixel(1,t))
        p.setPen(QtGui.QColor('#aaaaaa'));p.drawRect(r)
        for v in (0.,.5,1.):
            q=self.point_to_pixel(v,0);p.drawText(QtCore.QPointF(q.x()-8,r.bottom()+18),format(v,'.1f'));q=self.point_to_pixel(0,v);p.drawText(QtCore.QPointF(7,q.y()+4),format(v,'.1f'))
        try:
            u=np.linspace(0,1,max(128,int(r.width())));ys=evaluate_profile(self.points,u);path=QtGui.QPainterPath();path.moveTo(self.point_to_pixel(0,float(ys[0])))
            for x,y in zip(u[1:],ys[1:]):path.lineTo(self.point_to_pixel(float(x),float(y)))
            p.save();p.setClipRect(r.adjusted(-2,-2,2,2));p.setPen(QtGui.QPen(QtGui.QColor('#eeeeee'),1.7));p.drawPath(path);p.restore()
        except ValueError:pass
        for i,row in enumerate(self.points):
            cp=self.point_to_pixel(*row[3:5]);selected=i in self.selected
            if selected and row[0]!=0:
                p.setPen(QtGui.QPen(QtGui.QColor('#d1a857'),1))
                for a,b in ((1,2),(5,6)):
                    h=self.point_to_pixel(row[a],row[b]);p.drawLine(cp,h);p.setBrush(QtGui.QColor('#e6bc68'));p.drawEllipse(h,3,3)
            p.setPen(QtGui.QPen(QtGui.QColor('#111111'),1));p.setBrush(QtGui.QColor('#ff665b' if selected else '#8cc4e5'));p.drawRect(QtCore.QRectF(cp.x()-4,cp.y()-4,8,8))
        if self.box:p.setPen(QtGui.QPen(QtGui.QColor('#80bded'),1,QtCore.Qt.DashLine));p.setBrush(QtCore.Qt.NoBrush);p.drawRect(self.box.normalized())
    def mousePressEvent(self,event):
        if event.button()!=QtCore.Qt.LeftButton:return
        self.setFocus();pos=event.position()
        for i in sorted(self.selected):
            row=self.points[i]
            if row[0] not in (2,3):continue
            for h in (1,5):
                if (self.point_to_pixel(row[h],row[h+1])-pos).manhattanLength()<10:self._remember();self.drag=('handle',i,h);return
        hits=[i for i,r in enumerate(self.points) if (self.point_to_pixel(*r[3:5])-pos).manhattanLength()<11]
        if hits:
            i=hits[0]
            if event.modifiers()&QtCore.Qt.ControlModifier:self.selected.symmetric_difference_update({i})
            elif i not in self.selected:self.selected={i}
            self._remember();self.drag=('points',self.pixel_to_point(pos));self.selectionChanged.emit();self.update();return
        x,y=self.pixel_to_point(pos)
        if 0<=x<=1 and 0<=y<=1 and abs(y-float(evaluate_profile(self.points,[x])[0]))*self.plot_rect().height()<8:
            self.add_point(x);self.drag=('points',self.pixel_to_point(pos));return
        if not event.modifiers()&QtCore.Qt.ControlModifier:self.selected=set()
        self.box=QtCore.QRectF(pos,pos);self.drag=('box',pos);self.selectionChanged.emit();self.update()
    def mouseMoveEvent(self,event):
        if not self.drag:return
        kind=self.drag[0];x,y=self.pixel_to_point(event.position())
        if kind=='points':
            old=self.drag[1]
            if self.selected:
                row=self.points[min(self.selected)];self.move_selected(row[3]+x-old[0],row[4]+y-old[1],remember=False)
            self.drag=('points',(x,y))
        elif kind=='handle':
            _,i,h=self.drag;r=self.points[i];r[h]=min(10,max(-10,x));r[h+1]=min(10,max(-10,y))
            if (h==1 and r[h]>r[3]) or (h==5 and r[h]<r[3]):r[h]=r[3];r[h+1]=r[4]
            if r[0]==2:
                other=5 if h==1 else 1;r[other]=2*r[3]-r[h];r[other+1]=2*r[4]-r[h+1]
            self._notify()
        else:self.box=QtCore.QRectF(self.drag[1],event.position());self.update()
    def mouseReleaseEvent(self,event):
        if self.box:
            rect=self.box.normalized();self.selected|={i for i,r in enumerate(self.points) if rect.contains(self.point_to_pixel(*r[3:5]))};self.box=None;self.selectionChanged.emit()
        self.drag=None;self.update()
    def keyPressEvent(self,event):
        if event.matches(QtGui.QKeySequence.Undo):self.undo()
        elif event.matches(QtGui.QKeySequence.Redo):self.redo()
        elif event.matches(QtGui.QKeySequence.Copy):self.copy_curve()
        elif event.matches(QtGui.QKeySequence.Paste):self.paste_curve()
        elif event.key() in (QtCore.Qt.Key_Delete,QtCore.Qt.Key_Backspace):self.remove_selected()
        else:super().keyPressEvent(event)
