# -*- coding: utf-8 -*-
###################################################################################
#
#  ThreadProfileCmd.py
#  
#  Copyright 2019 Mark Ganson <TheMarkster> mwganson at gmail
#  
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#  
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#  
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.
#  
#  
###################################################################################

__title__   = "ThreadProfile"
__author__  = "Mark Ganson <TheMarkster>"
__url__     = "https://github.com/mwganson/ThreadProfile"
__date__    = "2019.07.22"
__version__ = "1.00"
version = 1.00


from FreeCAD import Gui
from PySide import QtCore, QtGui

import FreeCAD, FreeCADGui, Part, os, math, re
__dir__ = os.path.dirname(__file__)
iconPath = os.path.join( __dir__, 'Resources', 'icons' )
keepToolbar = False

import math
import Part, Draft
from FreeCAD import Base
import FreeCADGui, Draft_rc
from PySide import QtCore
from PySide.QtCore import QT_TRANSLATE_NOOP
gui = True

from Draft import _DraftObject, getParam, _ViewProviderWire, formatObject, select

class _ThreadProfile(_DraftObject):
    "The ThreadProfile object"

    def __init__(self, obj):
        _DraftObject.__init__(self,obj,"ThreadProfile")
        obj.addProperty("App::PropertyFloat", "Version", "ThreadProfile", QT_TRANSLATE_NOOP("App::Property","The version of ThreadProfile Workbench used to create this object")).Version = version
        obj.addProperty("App::PropertyVectorList","Points","ThreadProfile", QT_TRANSLATE_NOOP("App::Property","The points of the B-spline"))
        obj.addProperty("App::PropertyBool","Closed","ThreadProfile",QT_TRANSLATE_NOOP("App::Property","If the B-spline is closed or not"))
        obj.addProperty("App::PropertyBool","MakeFace","ThreadProfile",QT_TRANSLATE_NOOP("App::Property","Create a face if this spline is closed"))
        obj.addProperty("App::PropertyArea","Area","ThreadProfile",QT_TRANSLATE_NOOP("App::Property","The area of this object"))
        obj.addProperty("App::PropertyLength", "MinorDiameter", "ThreadProfile", QT_TRANSLATE_NOOP("App::Property", "The minor diameter of the thread"))
        obj.addProperty("App::PropertyFloatList","internal_data","ThreadProfile",QT_TRANSLATE_NOOP("App::Property", "Data used to construct internal thread"))
        obj.addProperty("App::PropertyFloatList","external_data","ThreadProfile",QT_TRANSLATE_NOOP("App::Property", "Data used to construct external thread"))
        obj.addProperty("App::PropertyFloatConstraint", "Pitch", "ThreadProfile", QT_TRANSLATE_NOOP("App::Property", "Pitch of the thread, use 25.4 / TPI if in mm mode else 1 / TPI to convert from threads per inch"))
        #obj.addProperty("App::PropertyBool", "MakeExternalThread", "ThreadProfile", QT_TRANSLATE_NOOP("App::Property", "If True, make an external thread profile, if False, make an internal thread profile"))
        obj.addProperty("App::PropertyEnumeration", "InternalOrExternal", "ThreadProfile", QT_TRANSLATE_NOOP("App::Property", "Whether to make internal or external thread profile"))
        obj.InternalOrExternal=["Internal", "External"]
        obj.InternalOrExternal="External"
        obj.addProperty("App::PropertyIntegerConstraint", "Quality", "ThreadProfile", QT_TRANSLATE_NOOP("App::Property", "Quality of profile: 1 = highest quality, 12 = lowest quality, higher numbers improve performance, but degrade quality of profile, valid values = 1 through 12"))
        obj.addProperty("App::PropertyString", "Continuity", "ThreadProfile", QT_TRANSLATE_NOOP("App::Property", "Continuity of the produced BSpline -- readonly"))
        obj.addProperty("App::PropertyStringList", "Instructions", "ThreadProfile", QT_TRANSLATE_NOOP("App::Property", "Instructions")).Instructions=[\
"Expand this with the ... button to view instructions",\
"Sweep this object along a helix of the same pitch to produce your thread.",\
"Can be dragged and dropped into Part Design as you would a sketch.",\
"For internal threads you will need to cut the Sweep object out of a cylinder, or if using Part Design sweep it as a Subtractive Pipe.",\
"Always use Frenet mode",\
"The Minor Diameter is *NOT* the same as the Nominal Diameter.  You need to lookup the correct Minor Diameter to use for the desired Nominal Diameter and Pitch for the desired fit tolerance."
]
        obj.Quality = (1,1,12,1) #1 default, 1 minimum, 12 max, 1 step size
        obj.Pitch = (1,0,500,.1)
        obj.setEditorMode("internal_data", 2) #0 = normal, 1 = readonly, 2 = hidden
        obj.setEditorMode("Closed", 2)
        obj.setEditorMode("MakeFace", 2)
        obj.setEditorMode("external_data", 2)
        obj.setEditorMode("Area", 2)
        obj.setEditorMode("Version", 1)
        obj.setEditorMode("Continuity", 1)
        obj.MakeFace = getParam("fillmode",True)
        obj.Closed = True
        obj.Points = []

        self.assureProperties(obj)

    def assureProperties(self, obj): # for Compatibility with older versions
        if not hasattr(obj, "Parameterization"):
            obj.addProperty("App::PropertyFloat","Parameterization","ThreadProfile",QT_TRANSLATE_NOOP("App::Property","Parameterization factor"))
            obj.Parameterization = 1.0
            obj.setEditorMode("Parameterization", 2)
            self.knotSeq = []

    def parameterization (self, pts, a, closed):
        # Computes a knot Sequence for a set of points
        # fac (0-1) : parameterization factor
        # fac=0 -> Uniform / fac=0.5 -> Centripetal / fac=1.0 -> Chord-Length
        if closed: # we need to add the first point as the end point
            pts.append(pts[0])
        params = [0]
        for i in range(1,len(pts)):
            p = pts[i].sub(pts[i-1])
            pl = pow(p.Length,a)
            params.append(params[-1] + pl)
        return params

    def makePoints(self, obj):

        pitch = obj.Pitch
        minor_diameter = obj.MinorDiameter.Value
        if "external" in obj.InternalOrExternal.lower():
            external = True
        else:
            if "internal" in obj.InternalOrExternal.lower():
                external=False
            else:
                FreeCAD.Console.PrintWarning("ThreadProfile: Unable to determine internal or external thread type, using external\n")
                external=True
        step = obj.Quality #1 means do not skip any points, 2 means use every other, 3 every 3rd, etc.
        points = []
        alpha = 0

        if external:
            our_data = obj.external_data
        else:
            our_data = obj.internal_data
        for ii in range(0, len(our_data),step):
            alpha += math.pi * 2 / 720 * step
            od = our_data[ii]
            radius = minor_diameter / 2 + od * pitch
            x = math.cos(alpha) * radius
            y = math.sin(alpha) * radius
            points.append(Base.Vector(x,y,0))
            
        return points


    def onChanged(self, fp, prop):
        if prop == "Parameterization":
            if fp.Parameterization < 0.:
                fp.Parameterization = 0.
            if fp.Parameterization > 1.0:
                fp.Parameterization = 1.0

    def execute(self, obj):
        obj.Points = self.makePoints(obj)
        import Part
        self.assureProperties(obj)
        if obj.Points:
            self.knotSeq = self.parameterization(obj.Points, obj.Parameterization, obj.Closed)
            plm = obj.Placement
            if obj.Closed and (len(obj.Points) > 2):
                if obj.Points[0] == obj.Points[-1]:  # should not occur, but OCC will crash
                    FreeCAD.Console.PrintError(translate('draft',  "_ThreadProfile.createGeometry: Closed with same first/last Point. Geometry not updated.")+"\n")
                    return
                spline = Part.BSplineCurve()
                spline.interpolate(obj.Points, PeriodicFlag = True, Parameters = self.knotSeq)
                # DNC: bug fix: convert to face if closed
                shape = Part.Wire(spline.toShape())
                # Creating a face from a closed spline cannot be expected to always work
                # Usually, if the spline is not flat the call of Part.Face() fails
                try:
                    if hasattr(obj,"MakeFace"):
                        if obj.MakeFace:
                            shape = Part.Face(shape)
                    else:
                        shape = Part.Face(shape)
                except Part.OCCError:
                    pass
                obj.Shape = shape
                if hasattr(obj,"Area") and hasattr(shape,"Area"):
                    obj.Area = shape.Area
            else:
                spline = Part.BSplineCurve()
                spline.interpolate(obj.Points, PeriodicFlag = False, Parameters = self.knotSeq)
                shape = spline.toShape()
                obj.Shape = shape
                if hasattr(obj,"Area") and hasattr(shape,"Area"):
                    obj.Area = shape.Area
            obj.Continuity = spline.Continuity
            obj.Placement = plm
        obj.positionBySupport()

# for compatibility with older versions
_ViewProviderBSpline = _ViewProviderWire

def makeThreadProfile(minor_diameter=4.891,pitch=1,closed=True,placement=None,face=None,support=None,internal_or_external="External",internal_data=[],external_data=[]):
    '''minor_diameter=4.891,pitch=1,closed=True,placement=None,face=None,support=None,internal_or_external="External",internal_data=[],external_data=[]): Creates a thread profile object
that can be swept along a helix to produce a thread.  Code is based on Draft.makeBSpline()'''
    if not FreeCAD.ActiveDocument:
        FreeCAD.Console.PrintError("No active document. Aborting\n")
        return
    else: fname = "ThreadProfile"
    obj = FreeCAD.ActiveDocument.addObject("Part::Part2DObjectPython",fname)
    _ThreadProfile(obj)
    obj.Closed = closed
    obj.Support = support
    #allow to include custom thread profile for internal_data or external_data
    #these are 720 floats of the x-coordinates
    #of a thread profile with pitch=1 sketched on the xz plane
    #with x=0 at the minor radius of the profile
    #the element position is the z-coordinate / 720 (2 points per degree)
    #y-coordinate is always zero
    #the thread profile produced is a function of these values, minor diameter, and pitch
    if len(internal_data)==0:
        obj.internal_data = [0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.002405626122,0.004811252243,0.007216878365,0.009622504486,0.012028130608,0.01443375673,0.016839382851,0.019245008973,0.021650635095,0.024056261216,0.026461887338,0.028867513459,0.031273139581,0.033678765703,0.036084391824,0.038490017946,0.040895644068,0.043301270189,0.045706896311,0.048112522432,0.050518148554,0.052923774676,0.055329400797,0.057735026919,0.060140653041,0.062546279162,0.064951905284,0.067357531405,0.069763157527,0.072168783649,0.07457440977,0.076980035892,0.079385662014,0.081791288135,0.084196914257,0.086602540378,0.0890081665,0.091413792622,0.093819418743,0.096225044865,0.098630670987,0.101036297108,0.10344192323,0.105847549351,0.108253175473,0.110658801595,0.113064427716,0.115470053838,0.11787567996,0.120281306081,0.122686932203,0.125092558324,0.127498184446,0.129903810568,0.132309436689,0.134715062811,0.137120688933,0.139526315054,0.141931941176,0.144337567297,0.146743193419,0.149148819541,0.151554445662,0.153960071784,0.156365697906,0.158771324027,0.161176950149,0.16358257627,0.165988202392,0.168393828514,0.170799454635,0.173205080757,0.175610706879,0.178016333,0.180421959122,0.182827585243,0.185233211365,0.187638837487,0.190044463608,0.19245008973,0.194855715851,0.197261341973,0.199666968095,0.202072594216,0.204478220338,0.20688384646,0.209289472581,0.211695098703,0.214100724824,0.216506350946,0.218911977068,0.221317603189,0.223723229311,0.226128855433,0.228534481554,0.230940107676,0.233345733797,0.235751359919,0.238156986041,0.240562612162,0.242968238284,0.245373864406,0.247779490527,0.250185116649,0.25259074277,0.254996368892,0.257401995014,0.259807621135,0.262213247257,0.264618873379,0.2670244995,0.269430125622,0.271835751743,0.274241377865,0.276647003987,0.279052630108,0.28145825623,0.283863882352,0.286269508473,0.288675134595,0.291080760716,0.293486386838,0.29589201296,0.298297639081,0.300703265203,0.303108891325,0.305514517446,0.307920143568,0.310325769689,0.312731395811,0.315137021933,0.317542648054,0.319948274176,0.322353900298,0.324759526419,0.327165152541,0.329570778662,0.331976404784,0.334382030906,0.336787657027,0.339193283149,0.341598909271,0.344004535392,0.346410161514,0.348815787635,0.351221413757,0.353627039879,0.356032666,0.358438292122,0.360843918244,0.363249544365,0.365655170487,0.368060796608,0.37046642273,0.372872048852,0.375277674973,0.377683301095,0.380088927216,0.382494553338,0.38490017946,0.387305805581,0.389711431703,0.392117057825,0.394522683946,0.396928310068,0.399333936189,0.401739562311,0.404145188433,0.406550814554,0.408956440676,0.411362066798,0.413767692919,0.416173319041,0.418578945162,0.420984571284,0.423390197406,0.425795823527,0.428201449649,0.430607075771,0.433012701892,0.435418328014,0.437823954135,0.440229580257,0.442635206379,0.4450408325,0.447446458622,0.449852084744,0.452257710865,0.454663336987,0.457068963108,0.45947458923,0.461880215352,0.464285841473,0.466691467595,0.469097093717,0.471502719838,0.47390834596,0.476313972081,0.478719598203,0.481125224325,0.483530850446,0.485936476568,0.48834210269,0.490747728811,0.493153354933,0.495558981054,0.497964607176,0.500370233298,0.502775859419,0.505181485541,0.507587111663,0.509992737784,0.512398363906,0.514803990027,0.517209616149,0.519615242271,0.522020868392,0.524426494514,0.526832120636,0.529237746757,0.531643372879,0.534048999,0.536454625122,0.538860251244,0.541265877365,0.543571138211,0.545698019279,0.547673314821,0.549517290262,0.55124571874,0.5528711653,0.554403833171,0.55585214206,0.557223135528,0.558522775457,0.55975615972,0.560927686209,0.56204117857,0.563099984046,0.56410705064,0.5650649887,0.565976120619,0.56684252132,0.567666051537,0.568448385396,0.56919103344,0.56989536197,0.570562609407,0.571193900198,0.571790256698,0.572352609371,0.57288180558,0.573378617192,0.573843747176,0.57427783534,0.574681463337,0.57505515903,0.575399400317,0.575714618461,0.576001201008,0.576259494329,0.576489805835,0.576692405885,0.576867529433,0.577015377435,0.577136118024,0.577229887482,0.577296791017,0.577336903362,0.57735026919,0.577336903362,0.577296791017,0.577229887482,0.577136118024,0.577015377435,0.576867529433,0.576692405885,0.576489805835,0.576259494329,0.576001201008,0.575714618461,0.575399400317,0.57505515903,0.574681463337,0.57427783534,0.573843747176,0.573378617192,0.57288180558,0.572352609371,0.571790256698,0.571193900198,0.570562609407,0.56989536197,0.56919103344,0.568448385396,0.567666051537,0.56684252132,0.565976120619,0.5650649887,0.56410705064,0.563099984047,0.56204117857,0.560927686209,0.55975615972,0.558522775457,0.557223135528,0.55585214206,0.554403833171,0.552871165301,0.55124571874,0.549517290262,0.547673314821,0.545698019279,0.543571138211,0.541265877365,0.538860251244,0.536454625122,0.534048999001,0.531643372879,0.529237746757,0.526832120636,0.524426494514,0.522020868393,0.519615242271,0.517209616149,0.514803990028,0.512398363906,0.509992737784,0.507587111663,0.505181485541,0.50277585942,0.500370233298,0.497964607176,0.495558981055,0.493153354933,0.490747728811,0.48834210269,0.485936476568,0.483530850447,0.481125224325,0.478719598203,0.476313972082,0.47390834596,0.471502719838,0.469097093717,0.466691467595,0.464285841474,0.461880215352,0.45947458923,0.457068963109,0.454663336987,0.452257710865,0.449852084744,0.447446458622,0.445040832501,0.442635206379,0.440229580257,0.437823954136,0.435418328014,0.433012701892,0.430607075771,0.428201449649,0.425795823528,0.423390197406,0.420984571284,0.418578945163,0.416173319041,0.413767692919,0.411362066798,0.408956440676,0.406550814555,0.404145188433,0.401739562311,0.39933393619,0.396928310068,0.394522683946,0.392117057825,0.389711431703,0.387305805582,0.38490017946,0.382494553338,0.380088927217,0.377683301095,0.375277674973,0.372872048852,0.37046642273,0.368060796609,0.365655170487,0.363249544365,0.360843918244,0.358438292122,0.356032666001,0.353627039879,0.351221413757,0.348815787636,0.346410161514,0.344004535392,0.341598909271,0.339193283149,0.336787657028,0.334382030906,0.331976404784,0.329570778663,0.327165152541,0.324759526419,0.322353900298,0.319948274176,0.317542648055,0.315137021933,0.312731395811,0.31032576969,0.307920143568,0.305514517446,0.303108891325,0.300703265203,0.298297639082,0.29589201296,0.293486386838,0.291080760717,0.288675134595,0.286269508473,0.283863882352,0.28145825623,0.279052630109,0.276647003987,0.274241377865,0.271835751744,0.269430125622,0.2670244995,0.264618873379,0.262213247257,0.259807621136,0.257401995014,0.254996368892,0.252590742771,0.250185116649,0.247779490527,0.245373864406,0.242968238284,0.240562612163,0.238156986041,0.235751359919,0.233345733798,0.230940107676,0.228534481554,0.226128855433,0.223723229311,0.22131760319,0.218911977068,0.216506350946,0.214100724825,0.211695098703,0.209289472581,0.20688384646,0.204478220338,0.202072594217,0.199666968095,0.197261341973,0.194855715852,0.19245008973,0.190044463608,0.187638837487,0.185233211365,0.182827585244,0.180421959122,0.178016333,0.175610706879,0.173205080757,0.170799454636,0.168393828514,0.165988202392,0.163582576271,0.161176950149,0.158771324027,0.156365697906,0.153960071784,0.151554445663,0.149148819541,0.146743193419,0.144337567298,0.141931941176,0.139526315054,0.137120688933,0.134715062811,0.13230943669,0.129903810568,0.127498184446,0.125092558325,0.122686932203,0.120281306081,0.11787567996,0.115470053838,0.113064427717,0.110658801595,0.108253175473,0.105847549352,0.10344192323,0.101036297108,0.098630670987,0.096225044865,0.093819418744,0.091413792622,0.0890081665,0.086602540379,0.084196914257,0.081791288135,0.079385662014,0.076980035892,0.074574409771,0.072168783649,0.069763157527,0.067357531406,0.064951905284,0.062546279162,0.060140653041,0.057735026919,0.055329400798,0.052923774676,0.050518148554,0.048112522433,0.045706896311,0.043301270189,0.040895644068,0.038490017946,0.036084391825,0.033678765703,0.031273139581,0.02886751346,0.026461887338,0.024056261216,0.021650635095,0.019245008973,0.016839382852,0.01443375673,0.012028130608,0.009622504487,0.007216878365,0.004811252244,0.002405626122]
    if len(external_data)==0:
        obj.external_data = [-0.002353874267,-0.004610521688,-0.006778280188,-0.008864283825,-0.010874693731,-0.012814874909,-0.014689533648,-0.016502825791,-0.018258443075,-0.019959682748,-0.021609504262,-0.023210575868,-0.024765313218,-0.026275911608,-0.027744373085,-0.029172529388,-0.030562061489,-0.031914516323,-0.033231321182,-0.034513796181,-0.035763165074,-0.036980564707,-0.038167053291,-0.039323617685,-0.040451179823,-0.041550602408,-0.042622693966,-0.043668213361,-0.04468787382,-0.045682346547,-0.046652263972,-0.047598222668,-0.048520785999,-0.049420486507,-0.050297828076,-0.051153287908,-0.051987318311,-0.052800348341,-0.05359278529,-0.05436501606,-0.055117408419,-0.055850312148,-0.056564060107,-0.057258969208,-0.057935341316,-0.058593464082,-0.059233611709,-0.059856045664,-0.06046101534,-0.061048758664,-0.061619502667,-0.062173464009,-0.062710849475,-0.063231856427,-0.06373667323,-0.064225479652,-0.06469844723,-0.06515573962,-0.065597512915,-0.066023915948,-0.066435090577,-0.066831171941,-0.067212288714,-0.067578563329,-0.067930112196,-0.068267045903,-0.068589469403,-0.06889748219,-0.069191178464,-0.069470647283,-0.069735972706,-0.069987233927,-0.070224505396,-0.070447856939,-0.070657353858,-0.070853057037,-0.071035023027,-0.071203304134,-0.071357948492,-0.071499000139,-0.071626499073,-0.071740481317,-0.071840978965,-0.071928020232,-0.072001629489,-0.072061827303,-0.07210863046,-0.072142051993,-0.072162101198,-0.072168783647,-0.072162101198,-0.072142051993,-0.07210863046,-0.072061827303,-0.072001629489,-0.071928020232,-0.071840978965,-0.071740481317,-0.071626499073,-0.071499000139,-0.071357948492,-0.071203304134,-0.071035023027,-0.070853057037,-0.070657353858,-0.070447856939,-0.070224505396,-0.069987233927,-0.069735972706,-0.069470647283,-0.069191178464,-0.06889748219,-0.068589469403,-0.068267045903,-0.067930112196,-0.067578563329,-0.067212288714,-0.066831171941,-0.066435090577,-0.066023915948,-0.065597512915,-0.06515573962,-0.06469844723,-0.064225479652,-0.06373667323,-0.063231856427,-0.062710849475,-0.062173464009,-0.061619502667,-0.061048758664,-0.06046101534,-0.059856045664,-0.059233611709,-0.058593464082,-0.057935341316,-0.057258969208,-0.056564060107,-0.055850312148,-0.055117408419,-0.05436501606,-0.05359278529,-0.052800348341,-0.051987318311,-0.051153287908,-0.050297828076,-0.049420486507,-0.048520785999,-0.047598222668,-0.046652263972,-0.045682346547,-0.04468787382,-0.043668213361,-0.042622693966,-0.041550602408,-0.040451179823,-0.039323617685,-0.038167053291,-0.036980564707,-0.035763165074,-0.034513796181,-0.033231321182,-0.031914516323,-0.030562061489,-0.029172529388,-0.027744373085,-0.026275911608,-0.024765313218,-0.023210575868,-0.021609504262,-0.019959682748,-0.018258443075,-0.016502825791,-0.014689533648,-0.012814874909,-0.010874693731,-0.008864283825,-0.006778280188,-0.004610521688,-0.002353874267,-1e-12,0.002405626125,0.004811252246,0.007216878368,0.009622504489,0.012028130611,0.014433756733,0.016839382854,0.019245008976,0.021650635097,0.024056261219,0.026461887341,0.028867513462,0.031273139584,0.033678765706,0.036084391827,0.038490017949,0.04089564407,0.043301270192,0.045706896314,0.048112522435,0.050518148557,0.052923774678,0.0553294008,0.057735026922,0.060140653043,0.062546279165,0.064951905286,0.067357531408,0.06976315753,0.072168783651,0.074574409773,0.076980035894,0.079385662016,0.081791288138,0.084196914259,0.086602540381,0.089008166503,0.091413792624,0.093819418746,0.096225044867,0.098630670989,0.101036297111,0.103441923232,0.105847549354,0.108253175475,0.110658801597,0.113064427719,0.11547005384,0.117875679962,0.120281306083,0.122686932205,0.125092558327,0.127498184448,0.12990381057,0.132309436692,0.134715062813,0.137120688935,0.139526315056,0.141931941178,0.1443375673,0.146743193421,0.149148819543,0.151554445664,0.153960071786,0.156365697908,0.158771324029,0.161176950151,0.163582576272,0.165988202394,0.168393828516,0.170799454637,0.173205080759,0.175610706881,0.178016333002,0.180421959124,0.182827585245,0.185233211367,0.187638837489,0.19004446361,0.192450089732,0.194855715853,0.197261341975,0.199666968097,0.202072594218,0.20447822034,0.206883846461,0.209289472583,0.211695098705,0.214100724826,0.216506350948,0.218911977069,0.221317603191,0.223723229313,0.226128855434,0.228534481556,0.230940107678,0.233345733799,0.235751359921,0.238156986042,0.240562612164,0.242968238286,0.245373864407,0.247779490529,0.25018511665,0.252590742772,0.254996368894,0.257401995015,0.259807621137,0.262213247258,0.26461887338,0.267024499502,0.269430125623,0.271835751745,0.274241377867,0.276647003988,0.27905263011,0.281458256231,0.283863882353,0.286269508475,0.288675134596,0.291080760718,0.293486386839,0.295892012961,0.298297639083,0.300703265204,0.303108891326,0.305514517447,0.307920143569,0.310325769691,0.312731395812,0.315137021934,0.317542648056,0.319948274177,0.322353900299,0.32475952642,0.327165152542,0.329570778664,0.331976404785,0.334382030907,0.336787657028,0.33919328315,0.341598909272,0.344004535393,0.346410161515,0.348815787636,0.351221413758,0.35362703988,0.356032666001,0.358438292123,0.360843918245,0.363249544366,0.365655170488,0.368060796609,0.370466422731,0.372872048853,0.375277674974,0.377683301096,0.380088927217,0.382494553339,0.384900179461,0.387305805582,0.389711431704,0.392117057825,0.394522683947,0.396928310069,0.39933393619,0.401739562312,0.404145188433,0.406550814555,0.408956440677,0.411362066798,0.41376769292,0.416173319042,0.418578945163,0.420984571285,0.423390197406,0.425795823528,0.42820144965,0.430607075771,0.433012701893,0.435418328014,0.437823954136,0.440229580258,0.442635206379,0.445040832501,0.447446458622,0.449852084744,0.452257710866,0.454663336987,0.457068963109,0.459474589231,0.461880215352,0.464285841474,0.466691467595,0.469097093717,0.471502719839,0.47390834596,0.476313972082,0.478719598203,0.481125224325,0.483530850447,0.485936476568,0.48834210269,0.490747728811,0.493153354933,0.495558981055,0.497964607176,0.500370233298,0.50277585942,0.505181485541,0.507587111663,0.509992737784,0.512398363906,0.514803990028,0.517209616149,0.519615242271,0.522020868392,0.524426494514,0.526832120636,0.529237746757,0.531643372879,0.534048999,0.536454625122,0.538860251244,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.541265877365,0.538860251244,0.536454625122,0.534048999,0.531643372879,0.529237746757,0.526832120636,0.524426494514,0.522020868392,0.519615242271,0.517209616149,0.514803990027,0.512398363906,0.509992737784,0.507587111663,0.505181485541,0.502775859419,0.500370233298,0.497964607176,0.495558981054,0.493153354933,0.490747728811,0.48834210269,0.485936476568,0.483530850446,0.481125224325,0.478719598203,0.476313972081,0.47390834596,0.471502719838,0.469097093717,0.466691467595,0.464285841473,0.461880215352,0.45947458923,0.457068963108,0.454663336987,0.452257710865,0.449852084744,0.447446458622,0.4450408325,0.442635206379,0.440229580257,0.437823954135,0.435418328014,0.433012701892,0.430607075771,0.428201449649,0.425795823527,0.423390197406,0.420984571284,0.418578945162,0.416173319041,0.413767692919,0.411362066798,0.408956440676,0.406550814554,0.404145188433,0.401739562311,0.399333936189,0.396928310068,0.394522683946,0.392117057825,0.389711431703,0.387305805581,0.38490017946,0.382494553338,0.380088927217,0.377683301095,0.375277674973,0.372872048852,0.37046642273,0.368060796608,0.365655170487,0.363249544365,0.360843918244,0.358438292122,0.356032666,0.353627039879,0.351221413757,0.348815787635,0.346410161514,0.344004535392,0.341598909271,0.339193283149,0.336787657027,0.334382030906,0.331976404784,0.329570778662,0.327165152541,0.324759526419,0.322353900298,0.319948274176,0.317542648054,0.315137021933,0.312731395811,0.310325769689,0.307920143568,0.305514517446,0.303108891325,0.300703265203,0.298297639081,0.29589201296,0.293486386838,0.291080760716,0.288675134595,0.286269508473,0.283863882352,0.28145825623,0.279052630108,0.276647003987,0.274241377865,0.271835751743,0.269430125622,0.2670244995,0.264618873379,0.262213247257,0.259807621135,0.257401995014,0.254996368892,0.25259074277,0.250185116649,0.247779490527,0.245373864406,0.242968238284,0.240562612162,0.238156986041,0.235751359919,0.233345733797,0.230940107676,0.228534481554,0.226128855433,0.223723229311,0.221317603189,0.218911977068,0.216506350946,0.214100724824,0.211695098703,0.209289472581,0.20688384646,0.204478220338,0.202072594216,0.199666968095,0.197261341973,0.194855715851,0.19245008973,0.190044463608,0.187638837487,0.185233211365,0.182827585243,0.180421959122,0.178016333,0.175610706879,0.173205080757,0.170799454635,0.168393828514,0.165988202392,0.16358257627,0.161176950149,0.158771324027,0.156365697906,0.153960071784,0.151554445662,0.149148819541,0.146743193419,0.144337567297,0.141931941176,0.139526315054,0.137120688933,0.134715062811,0.132309436689,0.129903810568,0.127498184446,0.125092558324,0.122686932203,0.120281306081,0.11787567996,0.115470053838,0.113064427716,0.110658801595,0.108253175473,0.105847549351,0.10344192323,0.101036297108,0.098630670987,0.096225044865,0.093819418743,0.091413792622,0.0890081665,0.086602540378,0.084196914257,0.081791288135,0.079385662014,0.076980035892,0.07457440977,0.072168783649,0.069763157527,0.067357531405,0.064951905284,0.062546279162,0.060140653041,0.057735026919,0.055329400797,0.052923774676,0.050518148554,0.048112522432,0.045706896311,0.043301270189,0.040895644068,0.038490017946,0.036084391824,0.033678765703,0.031273139581,0.028867513459,0.026461887338,0.024056261216,0.021650635095,0.019245008973,0.016839382851,0.01443375673,0.012028130608,0.009622504486,0.007216878365,0.004811252243,0.002405626122]
    obj.Pitch = pitch #default pitch
    obj.MinorDiameter = minor_diameter #M6x1 internal 6g tolerance class is default
    obj.InternalOrExternal=internal_or_external
    if face != None:
        obj.MakeFace = face
    if placement: obj.Placement = placement
    if gui:
        _ViewProviderWire(obj.ViewObject)
        formatObject(obj)
        select(obj)

    return obj


def initialize():

    Gui.addCommand("ThreadProfileCreateObject", ThreadProfileCreateObjectCommandClass())
    Gui.addCommand("ThreadProfileSettings", ThreadProfileSettingsCommandClass())


#######################################################################################
# Keep Toolbar active even after leaving workbench

class ThreadProfileSettingsCommandClass(object):
    """Settings, currently only whether to keep toolbar after leaving workbench"""

    def __init__(self):
        pass        


    def GetResources(self):
        return {'Pixmap'  : os.path.join( iconPath , 'Settings.png') , # the name of an icon file available in the resources

            'MenuText': "&Settings" ,
            'ToolTip' : "Workbench settings dialog"}
 
    def Activated(self):
        doc = FreeCAD.ActiveDocument
        from PySide import QtGui
        window = QtGui.QApplication.activeWindow()
        pg = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/ThreadProfile")
        keep = pg.GetBool('KeepToolbar',True)
        mostRecentTypesLength = pg.GetInt('mruLength',5)
        items=["Keep the toolbar active","Do not keep the toolbar active"]
        item,ok = QtGui.QInputDialog.getItem(window,'ThreadProfile','Settings\n\nSelect the settings option\n',items,0,False)
        if ok and item == items[0]:
            keep = True
            pg.SetBool('KeepToolbar', keep)
        elif ok and item==items[1]:
            keep = False
            pg.SetBool('KeepToolbar', keep)
        return
   
    def IsActive(self):
        return True


#Gui.addCommand("ThreadProfileKeepToolbar", ThreadProfileKeepToolbarCommandClass())


####################################################################################
# Create the dynamic data container object

class ThreadProfileCreateObjectCommandClass(object):
    """Create Object command"""

    def GetResources(self):
        return {'Pixmap'  : os.path.join( iconPath , 'CreateObject.png') ,
            'MenuText': "&Create Object" ,
            'ToolTip' : "Create the ThreadProfile object to contain the custom properties"}
 
    def Activated(self):
        doc = FreeCAD.ActiveDocument
        doc.openTransaction("CreateObject")
        makeThreadProfile()
        doc.commitTransaction()

        doc.recompute()
        return
   
    def IsActive(self):
        if not FreeCAD.ActiveDocument:
            return False
        return True

    def getHelp(self):
        return ["Created with ThreadProfile (v"+str(version)+") workbench.",
                "This is a thread profile object built",
                "for sweepoing along a helix in either the",
                "Part or Part Design workbench."
                "installation of the ThreadProfile workbench is required.",
]

#Gui.addCommand("ThreadProfileCreateObject", ThreadProfileCreateObjectCommandClass())












#bs = makeThreadProfile()
##continuity = Part.BSplineCurve(points).Continuity
#App.ActiveDocument.recompute()
initialize()