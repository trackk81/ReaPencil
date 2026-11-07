//Maya ASCII 2025ff03 scene
//Name: RevToon_Intersections.ma
//Last modified: Thu, Nov 05, 2026 07:34:45 PM
//Codeset: 949
requires maya "2025ff03";
currentUnit -l centimeter -a degree -t film;
fileInfo "application" "maya";
fileInfo "product" "Maya 2025";
fileInfo "version" "2025";
fileInfo "cutIdentifier" "202512041342-b90de33065";
fileInfo "osv" "Windows 11 Pro v2009 (Build: 26200)";
fileInfo "UUID" "1F5E4BA4-482F-4B38-9176-9C867B76D81B";
createNode transform -s -n "persp";
	rename -uid "32E02E07-4412-0814-4547-CC8CD0C93E38";
	setAttr ".v" no;
	setAttr ".t" -type "double3" 28 21 28 ;
	setAttr ".r" -type "double3" -27.938352729602379 44.999999999999972 -5.172681101354183e-14 ;
createNode camera -s -n "perspShape" -p "persp";
	rename -uid "0466C0E2-4970-B223-C81B-EEAD4D92A5DD";
	setAttr -k off ".v" no;
	setAttr ".rnd" no;
	setAttr ".fl" 34.999999999999993;
	setAttr ".coi" 44.82186966202994;
	setAttr ".imn" -type "string" "persp";
	setAttr ".den" -type "string" "persp_depth";
	setAttr ".man" -type "string" "persp_mask";
	setAttr ".hc" -type "string" "viewSet -p %camera";
createNode transform -s -n "top";
	rename -uid "4F709BBE-4BBB-8CC6-FA39-9F8019717606";
	setAttr ".v" no;
	setAttr ".t" -type "double3" 0 1000.1 0 ;
	setAttr ".r" -type "double3" -90 0 0 ;
createNode camera -s -n "topShape" -p "top";
	rename -uid "5A835320-4003-182D-2CAF-C9A443EBD7E2";
	setAttr -k off ".v" no;
	setAttr ".rnd" no;
	setAttr ".coi" 1000.1;
	setAttr ".ow" 30;
	setAttr ".imn" -type "string" "top";
	setAttr ".den" -type "string" "top_depth";
	setAttr ".man" -type "string" "top_mask";
	setAttr ".hc" -type "string" "viewSet -t %camera";
	setAttr ".o" yes;
createNode transform -s -n "front";
	rename -uid "39BAEACC-418B-DE60-0299-BF9B074608D9";
	setAttr ".v" no;
	setAttr ".t" -type "double3" 0 0 1000.1 ;
createNode camera -s -n "frontShape" -p "front";
	rename -uid "7A604F71-4686-E62F-0A05-70A6339862D3";
	setAttr -k off ".v" no;
	setAttr ".rnd" no;
	setAttr ".coi" 1000.1;
	setAttr ".ow" 30;
	setAttr ".imn" -type "string" "front";
	setAttr ".den" -type "string" "front_depth";
	setAttr ".man" -type "string" "front_mask";
	setAttr ".hc" -type "string" "viewSet -f %camera";
	setAttr ".o" yes;
createNode transform -s -n "side";
	rename -uid "5D8C933C-43B8-D7CB-3B1C-ADA0D5EA5DA8";
	setAttr ".v" no;
	setAttr ".t" -type "double3" 1000.1 0 0 ;
	setAttr ".r" -type "double3" 0 90 0 ;
createNode camera -s -n "sideShape" -p "side";
	rename -uid "AFAEF687-45F5-5B82-8123-5083D7711E2E";
	setAttr -k off ".v" no;
	setAttr ".rnd" no;
	setAttr ".coi" 1000.1;
	setAttr ".ow" 30;
	setAttr ".imn" -type "string" "side";
	setAttr ".den" -type "string" "side_depth";
	setAttr ".man" -type "string" "side_mask";
	setAttr ".hc" -type "string" "viewSet -s %camera";
	setAttr ".o" yes;
createNode transform -n "IntersectionBlock";
	rename -uid "A0612753-47F2-07D1-44F8-17A45855499E";
createNode mesh -n "IntersectionBlockShape" -p "IntersectionBlock";
	rename -uid "010932D5-4CA3-F2BC-6BFB-AC8AA197C385";
	setAttr -k off ".v";
	setAttr ".vir" yes;
	setAttr ".vif" yes;
	setAttr ".uvst[0].uvsn" -type "string" "map1";
	setAttr ".cuvs" -type "string" "map1";
	setAttr ".dcc" -type "string" "Diffuse";
	setAttr ".covm[0]"  0 1 1;
	setAttr ".cdvm[0]"  0 1 1;
	setAttr ".ndt" 0;
createNode transform -n "IntersectingBeam";
	rename -uid "6AEC9CA1-4218-D9D6-FFBB-14A469D618DF";
	setAttr ".t" -type "double3" 0.1 0.25 0.15 ;
	setAttr ".r" -type "double3" 0 27 12.000000000000002 ;
createNode mesh -n "IntersectingBeamShape" -p "IntersectingBeam";
	rename -uid "305C3811-4A66-0D30-DCEE-8A8F8405936A";
	setAttr -k off ".v";
	setAttr ".vir" yes;
	setAttr ".vif" yes;
	setAttr ".uvst[0].uvsn" -type "string" "map1";
	setAttr ".cuvs" -type "string" "map1";
	setAttr ".dcc" -type "string" "Diffuse";
	setAttr ".covm[0]"  0 1 1;
	setAttr ".cdvm[0]"  0 1 1;
	setAttr ".ndt" 0;
createNode transform -n "IntersectionCamera1";
	rename -uid "6C854C82-4B59-460E-5278-C389BD9D149A";
	setAttr ".t" -type "double3" 5.4 4 7.8 ;
	setAttr ".r" -type "double3" -22.605212089025208 34.695153531233977 9.6709586693615697e-16 ;
createNode camera -n "IntersectionCameraShape1" -p "IntersectionCamera1";
	rename -uid "8C466224-4F83-85DD-5E64-D3954A275187";
	setAttr -k off ".v";
	setAttr ".fl" 50;
	setAttr ".fcp" 30;
	setAttr ".imn" -type "string" "IntersectionCamera1";
	setAttr ".den" -type "string" "IntersectionCamera1_depth";
	setAttr ".man" -type "string" "IntersectionCamera1_mask";
createNode transform -n "IntersectionKey";
	rename -uid "0F424734-444A-0163-CA2C-F9A3ECF78E58";
	setAttr ".r" -type "double3" -35 -25 0 ;
createNode directionalLight -n "IntersectionKeyShape" -p "IntersectionKey";
	rename -uid "B08C89C2-4A77-5042-C414-61896F77320F";
	setAttr -k off ".v";
	setAttr ".in" 0.85000002384185791;
createNode lightLinker -s -n "lightLinker1";
	rename -uid "112A94BD-4994-F3C2-89DA-5BBF7C7C99C9";
	setAttr -s 4 ".lnk";
	setAttr -s 4 ".slnk";
createNode displayLayerManager -n "layerManager";
	rename -uid "B7415CFE-4A96-7F6F-F05F-AF8CA2AA3EDC";
createNode displayLayer -n "defaultLayer";
	rename -uid "AAEC7337-4236-AC10-0DD6-60998BFF9971";
	setAttr ".ufem" -type "stringArray" 0  ;
createNode renderLayerManager -n "renderLayerManager";
	rename -uid "F3EB741D-4371-7A4B-8C2F-539B9B73096D";
createNode renderLayer -n "defaultRenderLayer";
	rename -uid "6AFFD7AF-4301-4F6B-D063-8D8C6DDD9738";
	setAttr ".g" yes;
createNode polyCube -n "polyCube1";
	rename -uid "3E1B83B9-41C3-2DE4-200A-B0977B7A6F41";
	setAttr ".w" 2.25;
	setAttr ".h" 2.1;
	setAttr ".d" 1.8;
createNode rampShader -n "BlockTeal";
	rename -uid "55B9371F-47D6-B1B3-AAAF-64A709D238D1";
	addAttr -ci true -sn "reaToonKind" -ln "reaToonKind" -dt "string";
	addAttr -ci true -uac -sn "reaToonBaseColor" -ln "reaToonBaseColor" -at "float3" 
		-nc 3;
	addAttr -ci true -sn "reaToonBaseColorR" -ln "reaToonBaseColorR" -min 0 -max 1 -at "float" 
		-p "reaToonBaseColor";
	addAttr -ci true -sn "reaToonBaseColorG" -ln "reaToonBaseColorG" -min 0 -max 1 -at "float" 
		-p "reaToonBaseColor";
	addAttr -ci true -sn "reaToonBaseColorB" -ln "reaToonBaseColorB" -min 0 -max 1 -at "float" 
		-p "reaToonBaseColor";
	addAttr -ci true -uac -sn "reaToonShadowColor" -ln "reaToonShadowColor" -at "float3" 
		-nc 3;
	addAttr -ci true -sn "reaToonShadowColorR" -ln "reaToonShadowColorR" -min 0 -max 
		1 -at "float" -p "reaToonShadowColor";
	addAttr -ci true -sn "reaToonShadowColorG" -ln "reaToonShadowColorG" -min 0 -max 
		1 -at "float" -p "reaToonShadowColor";
	addAttr -ci true -sn "reaToonShadowColorB" -ln "reaToonShadowColorB" -min 0 -max 
		1 -at "float" -p "reaToonShadowColor";
	addAttr -ci true -uac -sn "reaToonHighlightColor" -ln "reaToonHighlightColor" -at "float3" 
		-nc 3;
	addAttr -ci true -sn "reaToonHighlightColorR" -ln "reaToonHighlightColorR" -min 
		0 -max 1 -at "float" -p "reaToonHighlightColor";
	addAttr -ci true -sn "reaToonHighlightColorG" -ln "reaToonHighlightColorG" -min 
		0 -max 1 -at "float" -p "reaToonHighlightColor";
	addAttr -ci true -sn "reaToonHighlightColorB" -ln "reaToonHighlightColorB" -min 
		0 -max 1 -at "float" -p "reaToonHighlightColor";
	addAttr -ci true -k true -sn "reaToonThreshold" -ln "reaToonThreshold" -dv 0.5 -min 
		0 -max 1 -at "double";
	addAttr -ci true -k true -sn "reaToonHighlightThreshold" -ln "reaToonHighlightThreshold" 
		-dv 0.85 -min 0 -max 1 -at "double";
	addAttr -ci true -k true -sn "reaToonGradationOffset" -ln "reaToonGradationOffset" 
		-min -1 -max 1 -at "double";
	setAttr -s 3 ".clr";
	setAttr ".clr[0].clrp" 0;
	setAttr ".clr[0].clri" 0;
	setAttr ".clr[1].clri" 0;
	setAttr ".clr[2].clri" 0;
	setAttr ".it[0].itp" 0;
	setAttr ".it[0].itc" -type "float3" 0 0 0 ;
	setAttr ".it[0].iti" 1;
	setAttr ".ic[0].icp" 0;
	setAttr ".ic[0].icc" -type "float3" 0 0 0 ;
	setAttr ".ic[0].ici" 1;
	setAttr -s 2 ".sro[0:1]"  0 1 2 0.5 0.5 2;
	setAttr ".sc[0].scp" 0;
	setAttr ".sc[0].scc" -type "float3" 0.5 0.5 0.5 ;
	setAttr ".sc[0].sci" 1;
	setAttr ".rfl[0]"  0 1 1;
	setAttr ".env[0].envp" 0;
	setAttr ".env[0].envc" -type "float3" 0 0 0 ;
	setAttr ".env[0].envi" 1;
	setAttr ".reaToonKind" -type "string" "material";
	setAttr ".reaToonBaseColor" -type "float3" 0.16 0.62 0.62 ;
	setAttr ".reaToonShadowColor" -type "float3" 0.079999998 0.28999999 0.33000001 ;
	setAttr ".reaToonHighlightColor" -type "float3" 0.40000001 0.81 0.76999998 ;
	setAttr -k on ".reaToonThreshold";
	setAttr -k on ".reaToonHighlightThreshold";
createNode shadingEngine -n "BlockTealSG";
	rename -uid "FBDE66E5-48E3-0500-CBC2-44B15AEB55C8";
	setAttr ".ihi" 0;
	setAttr ".ro" yes;
createNode materialInfo -n "materialInfo1";
	rename -uid "07092B81-4C4D-A8F1-4AC4-70B1AB77F9BA";
createNode polyCube -n "polyCube2";
	rename -uid "F387E839-4DFA-CF58-D81D-5F9D9CD1CF26";
	setAttr ".w" 3.8;
	setAttr ".h" 0.7;
	setAttr ".d" 1.05;
createNode rampShader -n "BeamGold";
	rename -uid "74CE50A1-4134-D527-B7F4-B5BA70A20E70";
	addAttr -ci true -sn "reaToonKind" -ln "reaToonKind" -dt "string";
	addAttr -ci true -uac -sn "reaToonBaseColor" -ln "reaToonBaseColor" -at "float3" 
		-nc 3;
	addAttr -ci true -sn "reaToonBaseColorR" -ln "reaToonBaseColorR" -min 0 -max 1 -at "float" 
		-p "reaToonBaseColor";
	addAttr -ci true -sn "reaToonBaseColorG" -ln "reaToonBaseColorG" -min 0 -max 1 -at "float" 
		-p "reaToonBaseColor";
	addAttr -ci true -sn "reaToonBaseColorB" -ln "reaToonBaseColorB" -min 0 -max 1 -at "float" 
		-p "reaToonBaseColor";
	addAttr -ci true -uac -sn "reaToonShadowColor" -ln "reaToonShadowColor" -at "float3" 
		-nc 3;
	addAttr -ci true -sn "reaToonShadowColorR" -ln "reaToonShadowColorR" -min 0 -max 
		1 -at "float" -p "reaToonShadowColor";
	addAttr -ci true -sn "reaToonShadowColorG" -ln "reaToonShadowColorG" -min 0 -max 
		1 -at "float" -p "reaToonShadowColor";
	addAttr -ci true -sn "reaToonShadowColorB" -ln "reaToonShadowColorB" -min 0 -max 
		1 -at "float" -p "reaToonShadowColor";
	addAttr -ci true -uac -sn "reaToonHighlightColor" -ln "reaToonHighlightColor" -at "float3" 
		-nc 3;
	addAttr -ci true -sn "reaToonHighlightColorR" -ln "reaToonHighlightColorR" -min 
		0 -max 1 -at "float" -p "reaToonHighlightColor";
	addAttr -ci true -sn "reaToonHighlightColorG" -ln "reaToonHighlightColorG" -min 
		0 -max 1 -at "float" -p "reaToonHighlightColor";
	addAttr -ci true -sn "reaToonHighlightColorB" -ln "reaToonHighlightColorB" -min 
		0 -max 1 -at "float" -p "reaToonHighlightColor";
	addAttr -ci true -k true -sn "reaToonThreshold" -ln "reaToonThreshold" -dv 0.5 -min 
		0 -max 1 -at "double";
	addAttr -ci true -k true -sn "reaToonHighlightThreshold" -ln "reaToonHighlightThreshold" 
		-dv 0.85 -min 0 -max 1 -at "double";
	addAttr -ci true -k true -sn "reaToonGradationOffset" -ln "reaToonGradationOffset" 
		-min -1 -max 1 -at "double";
	setAttr -s 3 ".clr";
	setAttr ".clr[0].clrp" 0;
	setAttr ".clr[0].clri" 0;
	setAttr ".clr[1].clri" 0;
	setAttr ".clr[2].clri" 0;
	setAttr ".it[0].itp" 0;
	setAttr ".it[0].itc" -type "float3" 0 0 0 ;
	setAttr ".it[0].iti" 1;
	setAttr ".ic[0].icp" 0;
	setAttr ".ic[0].icc" -type "float3" 0 0 0 ;
	setAttr ".ic[0].ici" 1;
	setAttr -s 2 ".sro[0:1]"  0 1 2 0.5 0.5 2;
	setAttr ".sc[0].scp" 0;
	setAttr ".sc[0].scc" -type "float3" 0.5 0.5 0.5 ;
	setAttr ".sc[0].sci" 1;
	setAttr ".rfl[0]"  0 1 1;
	setAttr ".env[0].envp" 0;
	setAttr ".env[0].envc" -type "float3" 0 0 0 ;
	setAttr ".env[0].envi" 1;
	setAttr ".reaToonKind" -type "string" "material";
	setAttr ".reaToonBaseColor" -type "float3" 0.94999999 0.61000001 0.2 ;
	setAttr ".reaToonShadowColor" -type "float3" 0.47999999 0.23 0.079999998 ;
	setAttr ".reaToonHighlightColor" -type "float3" 1 0.82999998 0.44 ;
	setAttr -k on ".reaToonThreshold";
	setAttr -k on ".reaToonHighlightThreshold";
createNode shadingEngine -n "BeamGoldSG";
	rename -uid "507A84D2-4DB2-B659-3EBE-91A67419DF99";
	setAttr ".ihi" 0;
	setAttr ".ro" yes;
createNode materialInfo -n "materialInfo2";
	rename -uid "3075C89F-4EAE-D47B-30CF-27BEDBA61CC5";
createNode network -n "reaToonSettings";
	rename -uid "9EFB05C9-43DB-C323-26CD-29B550463E76";
	addAttr -ci true -sn "reaToonKind" -ln "reaToonKind" -dt "string";
	addAttr -ci true -sn "reaToonSettingsJson" -ln "reaToonSettingsJson" -dt "string";
	setAttr ".reaToonKind" -type "string" "settings";
	setAttr ".reaToonSettingsJson" -type "string" "{\"background\": [0.96, 0.97, 0.96], \"crease\": true, \"crease_angle\": 40.0, \"dash_length\": 0.0, \"depth_bias\": 0.002, \"distance_reduction\": 0.0, \"hard_edges\": true, \"height\": 480, \"hidden_color\": [0.5, 0.5, 0.6], \"hidden_lines\": false, \"intersection_tolerance\": 1e-07, \"intersections\": true, \"line_color\": [0.045, 0.065, 0.09], \"line_width\": 2.0, \"material_boundaries\": true, \"open_edges\": true, \"outline\": true, \"seed\": 1, \"selected_edges\": true, \"self_intersections\": false, \"supersample\": 2, \"taper\": 0.0, \"width\": 640, \"width_variation\": 0.0, \"wireframe\": false}";
createNode script -n "uiConfigurationScriptNode";
	rename -uid "F416E123-44EC-879B-FB92-FB811C5DA13F";
	setAttr ".b" -type "string" "// Maya Mel UI Configuration File.\n// No UI generated in batch mode.\n";
	setAttr ".st" 3;
createNode script -n "sceneConfigurationScriptNode";
	rename -uid "94EA9DDF-4299-17C8-3F43-3B8FA827ADDB";
	setAttr ".b" -type "string" "playbackOptions -min 1 -max 120 -ast 1 -aet 200 ";
	setAttr ".st" 6;
select -ne :time1;
	setAttr ".o" 1;
	setAttr ".unw" 1;
select -ne :hardwareRenderingGlobals;
	setAttr ".otfna" -type "stringArray" 22 "NURBS Curves" "NURBS Surfaces" "Polygons" "Subdiv Surface" "Particles" "Particle Instance" "Fluids" "Strokes" "Image Planes" "UI" "Lights" "Cameras" "Locators" "Joints" "IK Handles" "Deformers" "Motion Trails" "Components" "Hair Systems" "Follicles" "Misc. UI" "Ornaments"  ;
	setAttr ".otfva" -type "Int32Array" 22 0 1 1 1 1 1
		 1 1 1 0 0 0 0 0 0 0 0 0
		 0 0 0 0 ;
	setAttr ".fprt" yes;
	setAttr ".rtfm" 1;
select -ne :renderPartition;
	setAttr -s 4 ".st";
select -ne :renderGlobalsList1;
select -ne :defaultShaderList1;
	setAttr -s 7 ".s";
select -ne :postProcessList1;
	setAttr -s 2 ".p";
select -ne :defaultRenderingList1;
select -ne :lightList1;
select -ne :standardSurface1;
	setAttr ".bc" -type "float3" 0.40000001 0.40000001 0.40000001 ;
	setAttr ".sr" 0.5;
select -ne :initialShadingGroup;
	setAttr ".ro" yes;
select -ne :initialParticleSE;
	setAttr ".ro" yes;
select -ne :defaultRenderGlobals;
	addAttr -ci true -h true -sn "dss" -ln "defaultSurfaceShader" -dt "string";
	setAttr ".dss" -type "string" "standardSurface1";
select -ne :defaultResolution;
	setAttr ".pa" 1;
select -ne :defaultLightSet;
select -ne :defaultColorMgtGlobals;
	setAttr ".cfe" yes;
	setAttr ".cfp" -type "string" "<MAYA_RESOURCES>/OCIO-configs/Maya2022-default/config.ocio";
	setAttr ".vtn" -type "string" "ACES 1.0 SDR-video (sRGB)";
	setAttr ".vn" -type "string" "ACES 1.0 SDR-video";
	setAttr ".dn" -type "string" "sRGB";
	setAttr ".wsn" -type "string" "ACEScg";
	setAttr ".otn" -type "string" "ACES 1.0 SDR-video (sRGB)";
	setAttr ".potn" -type "string" "ACES 1.0 SDR-video (sRGB)";
select -ne :hardwareRenderGlobals;
	setAttr ".ctrs" 256;
	setAttr ".btrs" 512;
connectAttr "polyCube1.out" "IntersectionBlockShape.i";
connectAttr "polyCube2.out" "IntersectingBeamShape.i";
relationship "link" ":lightLinker1" ":initialShadingGroup.message" ":defaultLightSet.message";
relationship "link" ":lightLinker1" ":initialParticleSE.message" ":defaultLightSet.message";
relationship "link" ":lightLinker1" "BlockTealSG.message" ":defaultLightSet.message";
relationship "link" ":lightLinker1" "BeamGoldSG.message" ":defaultLightSet.message";
relationship "shadowLink" ":lightLinker1" ":initialShadingGroup.message" ":defaultLightSet.message";
relationship "shadowLink" ":lightLinker1" ":initialParticleSE.message" ":defaultLightSet.message";
relationship "shadowLink" ":lightLinker1" "BlockTealSG.message" ":defaultLightSet.message";
relationship "shadowLink" ":lightLinker1" "BeamGoldSG.message" ":defaultLightSet.message";
connectAttr "layerManager.dli[0]" "defaultLayer.id";
connectAttr "renderLayerManager.rlmi[0]" "defaultRenderLayer.rlid";
connectAttr "BlockTeal.reaToonShadowColor" "BlockTeal.clr[0].clrc";
connectAttr "BlockTeal.reaToonBaseColor" "BlockTeal.clr[1].clrc";
connectAttr "BlockTeal.reaToonThreshold" "BlockTeal.clr[1].clrp";
connectAttr "BlockTeal.reaToonHighlightColor" "BlockTeal.clr[2].clrc";
connectAttr "BlockTeal.reaToonHighlightThreshold" "BlockTeal.clr[2].clrp";
connectAttr "BlockTeal.oc" "BlockTealSG.ss";
connectAttr "IntersectionBlockShape.iog" "BlockTealSG.dsm" -na;
connectAttr "BlockTealSG.msg" "materialInfo1.sg";
connectAttr "BeamGold.reaToonShadowColor" "BeamGold.clr[0].clrc";
connectAttr "BeamGold.reaToonBaseColor" "BeamGold.clr[1].clrc";
connectAttr "BeamGold.reaToonThreshold" "BeamGold.clr[1].clrp";
connectAttr "BeamGold.reaToonHighlightColor" "BeamGold.clr[2].clrc";
connectAttr "BeamGold.reaToonHighlightThreshold" "BeamGold.clr[2].clrp";
connectAttr "BeamGold.oc" "BeamGoldSG.ss";
connectAttr "IntersectingBeamShape.iog" "BeamGoldSG.dsm" -na;
connectAttr "BeamGoldSG.msg" "materialInfo2.sg";
connectAttr "BlockTealSG.pa" ":renderPartition.st" -na;
connectAttr "BeamGoldSG.pa" ":renderPartition.st" -na;
connectAttr "BlockTeal.msg" ":defaultShaderList1.s" -na;
connectAttr "BeamGold.msg" ":defaultShaderList1.s" -na;
connectAttr "defaultRenderLayer.msg" ":defaultRenderingList1.r" -na;
connectAttr "IntersectionKeyShape.ltd" ":lightList1.l" -na;
connectAttr "IntersectionKey.iog" ":defaultLightSet.dsm" -na;
dataStructure -fmt "raw" -as "name=externalContentTable:string=node:string=key:string=upath:uint32=upathcrc:string=rpath:string=roles";
applyMetadata -fmt "raw" -v "channel\nname externalContentTable\nstream\nname v1.0\nindexType numeric\nstructure externalContentTable\n0\n\"|IntersectionKey|IntersectionKeyShape\" \"dmapName\" \"depthmap\" 2097411553 \"\" \"sourceImages\"\nendStream\nendChannel\nendAssociations\n" 
		-scn;
// End of RevToon_Intersections.ma
