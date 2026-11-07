//Maya ASCII 2025ff03 scene
//Name: ReaToon_Demo.ma
//Last modified: Thu, Nov 05, 2026 07:11:15 PM
//Codeset: 949
requires maya "2025ff03";
currentUnit -l centimeter -a degree -t film;
fileInfo "application" "maya";
fileInfo "product" "Maya 2025";
fileInfo "version" "2025";
fileInfo "cutIdentifier" "202512041342-b90de33065";
fileInfo "osv" "Windows 11 Pro v2009 (Build: 26200)";
fileInfo "UUID" "1CF0FAA5-4A5B-466F-56DF-6E8FBA248AF7";
createNode transform -s -n "persp";
	rename -uid "30040ACF-41C3-4081-70C4-E7B597A633C1";
	setAttr ".v" no;
	setAttr ".t" -type "double3" 28 21 28 ;
	setAttr ".r" -type "double3" -27.938352729602379 44.999999999999972 -5.172681101354183e-14 ;
createNode camera -s -n "perspShape" -p "persp";
	rename -uid "5F5675C5-48BA-C366-C9FB-309CF4CABD47";
	setAttr -k off ".v" no;
	setAttr ".rnd" no;
	setAttr ".fl" 34.999999999999993;
	setAttr ".coi" 44.82186966202994;
	setAttr ".imn" -type "string" "persp";
	setAttr ".den" -type "string" "persp_depth";
	setAttr ".man" -type "string" "persp_mask";
	setAttr ".hc" -type "string" "viewSet -p %camera";
createNode transform -s -n "top";
	rename -uid "94442844-4A63-8E52-806B-D6B19AA0A6C7";
	setAttr ".v" no;
	setAttr ".t" -type "double3" 0 1000.1 0 ;
	setAttr ".r" -type "double3" -90 0 0 ;
createNode camera -s -n "topShape" -p "top";
	rename -uid "23979AAF-45E9-2ECC-6AD2-82B29A59C6F6";
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
	rename -uid "BDDD7BFF-4CB4-19E8-5634-90A081601DD6";
	setAttr ".v" no;
	setAttr ".t" -type "double3" 0 0 1000.1 ;
createNode camera -s -n "frontShape" -p "front";
	rename -uid "B3DE797C-482E-61F3-4991-5F82C5A60800";
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
	rename -uid "892536B8-4802-1182-D063-15BDDD838640";
	setAttr ".v" no;
	setAttr ".t" -type "double3" 1000.1 0 0 ;
	setAttr ".r" -type "double3" 0 90 0 ;
createNode camera -s -n "sideShape" -p "side";
	rename -uid "1552CD80-4EC1-A7FC-599F-44B937D714E2";
	setAttr -k off ".v" no;
	setAttr ".rnd" no;
	setAttr ".coi" 1000.1;
	setAttr ".ow" 30;
	setAttr ".imn" -type "string" "side";
	setAttr ".den" -type "string" "side_depth";
	setAttr ".man" -type "string" "side_mask";
	setAttr ".hc" -type "string" "viewSet -s %camera";
	setAttr ".o" yes;
createNode transform -n "DemoBody";
	rename -uid "081617E8-4EE3-71D0-6C85-9A9A8DB87106";
	setAttr ".t" -type "double3" 0 1.25 0 ;
createNode mesh -n "DemoBodyShape" -p "DemoBody";
	rename -uid "9136A1E7-44F6-6F5D-A253-BCB988903583";
	setAttr -k off ".v";
	setAttr ".vir" yes;
	setAttr ".vif" yes;
	setAttr ".uvst[0].uvsn" -type "string" "map1";
	setAttr ".cuvs" -type "string" "map1";
	setAttr ".dcc" -type "string" "Diffuse";
	setAttr ".covm[0]"  0 1 1;
	setAttr ".cdvm[0]"  0 1 1;
	setAttr ".ndt" 0;
createNode transform -n "DemoHead";
	rename -uid "691FBECD-4C71-23A2-0799-7B8E81C98770";
	setAttr ".t" -type "double3" 0 2.35 0.03 ;
	setAttr ".s" -type "double3" 0.91 0.73 0.69 ;
createNode mesh -n "DemoHeadShape" -p "DemoHead";
	rename -uid "433D1A20-43B8-4641-1A18-C9954DAB6E7F";
	setAttr -k off ".v";
	setAttr ".vir" yes;
	setAttr ".vif" yes;
	setAttr ".uvst[0].uvsn" -type "string" "map1";
	setAttr ".cuvs" -type "string" "map1";
	setAttr ".dcc" -type "string" "Diffuse";
	setAttr ".covm[0]"  0 1 1;
	setAttr ".cdvm[0]"  0 1 1;
	setAttr ".ndt" 0;
createNode transform -n "LeftEye";
	rename -uid "D9614638-414C-CB4F-E5A1-61BF0048E317";
	setAttr ".t" -type "double3" -0.32 2.43 0.65 ;
	setAttr ".s" -type "double3" 0.105 0.15 0.075 ;
createNode mesh -n "LeftEyeShape" -p "LeftEye";
	rename -uid "900F9607-46D4-2B7B-67B3-67B51206324E";
	setAttr -k off ".v";
	setAttr ".vir" yes;
	setAttr ".vif" yes;
	setAttr ".uvst[0].uvsn" -type "string" "map1";
	setAttr ".cuvs" -type "string" "map1";
	setAttr ".dcc" -type "string" "Diffuse";
	setAttr ".covm[0]"  0 1 1;
	setAttr ".cdvm[0]"  0 1 1;
	setAttr ".ndt" 0;
createNode transform -n "RightEye";
	rename -uid "F6EC767B-48C8-5C16-01EC-4D9AF5ED5DF8";
	setAttr ".t" -type "double3" 0.32 2.43 0.65 ;
	setAttr ".s" -type "double3" 0.105 0.15 0.075 ;
createNode mesh -n "RightEyeShape" -p "RightEye";
	rename -uid "868111E9-482C-BB72-F0D1-A083582761A3";
	setAttr -k off ".v";
	setAttr ".vir" yes;
	setAttr ".vif" yes;
	setAttr ".uvst[0].uvsn" -type "string" "map1";
	setAttr ".cuvs" -type "string" "map1";
	setAttr ".dcc" -type "string" "Diffuse";
	setAttr ".covm[0]"  0 1 1;
	setAttr ".cdvm[0]"  0 1 1;
	setAttr ".ndt" 0;
createNode transform -n "LeftHand";
	rename -uid "3401D9BE-4228-76DA-ED6F-8585A721F12E";
	setAttr ".t" -type "double3" -0.95 1.3 0.05 ;
	setAttr ".s" -type "double3" 0.27 0.46 0.28 ;
createNode mesh -n "LeftHandShape" -p "LeftHand";
	rename -uid "E08B52B0-4508-004E-8BA6-86BD8F289638";
	setAttr -k off ".v";
	setAttr ".vir" yes;
	setAttr ".vif" yes;
	setAttr ".uvst[0].uvsn" -type "string" "map1";
	setAttr ".cuvs" -type "string" "map1";
	setAttr ".dcc" -type "string" "Diffuse";
	setAttr ".covm[0]"  0 1 1;
	setAttr ".cdvm[0]"  0 1 1;
	setAttr ".ndt" 0;
createNode transform -n "RightHand";
	rename -uid "90EE328A-45E4-F44A-48CD-09A7191AC359";
	setAttr ".t" -type "double3" 0.95 1.3 0.05 ;
	setAttr ".s" -type "double3" 0.27 0.46 0.28 ;
createNode mesh -n "RightHandShape" -p "RightHand";
	rename -uid "6F79A3D0-41A9-0E48-A359-37AE98344A9E";
	setAttr -k off ".v";
	setAttr ".vir" yes;
	setAttr ".vif" yes;
	setAttr ".uvst[0].uvsn" -type "string" "map1";
	setAttr ".cuvs" -type "string" "map1";
	setAttr ".dcc" -type "string" "Diffuse";
	setAttr ".covm[0]"  0 1 1;
	setAttr ".cdvm[0]"  0 1 1;
	setAttr ".ndt" 0;
createNode transform -n "LeftFoot";
	rename -uid "034B2999-4FFD-C23F-0670-D89D3E5743C0";
	setAttr ".t" -type "double3" -0.37 0.35 0.18 ;
	setAttr ".s" -type "double3" 0.32 0.33 0.47 ;
createNode mesh -n "LeftFootShape" -p "LeftFoot";
	rename -uid "CD542B2D-4A7D-26D8-454D-9FBC8C3DDDD1";
	setAttr -k off ".v";
	setAttr ".vir" yes;
	setAttr ".vif" yes;
	setAttr ".uvst[0].uvsn" -type "string" "map1";
	setAttr ".cuvs" -type "string" "map1";
	setAttr ".dcc" -type "string" "Diffuse";
	setAttr ".covm[0]"  0 1 1;
	setAttr ".cdvm[0]"  0 1 1;
	setAttr ".ndt" 0;
createNode transform -n "RightFoot";
	rename -uid "862299C2-4F4B-76A0-9C52-98B91D32542D";
	setAttr ".t" -type "double3" 0.37 0.35 0.18 ;
	setAttr ".s" -type "double3" 0.32 0.33 0.47 ;
createNode mesh -n "RightFootShape" -p "RightFoot";
	rename -uid "62DC96AD-44F5-AA65-C403-FEABB81552A0";
	setAttr -k off ".v";
	setAttr ".vir" yes;
	setAttr ".vif" yes;
	setAttr ".uvst[0].uvsn" -type "string" "map1";
	setAttr ".cuvs" -type "string" "map1";
	setAttr ".dcc" -type "string" "Diffuse";
	setAttr ".covm[0]"  0 1 1;
	setAttr ".cdvm[0]"  0 1 1;
	setAttr ".ndt" 0;
createNode transform -n "Antenna";
	rename -uid "76EC87E0-44FD-9EE1-9EED-9898A744591A";
	setAttr ".t" -type "double3" 0 3.23 0.03 ;
	setAttr ".s" -type "double3" 0.13 0.13 0.13 ;
createNode mesh -n "AntennaShape" -p "Antenna";
	rename -uid "C6B5BF25-4268-846B-BB3C-EB86C3A8DD94";
	setAttr -k off ".v";
	setAttr ".vir" yes;
	setAttr ".vif" yes;
	setAttr ".uvst[0].uvsn" -type "string" "map1";
	setAttr ".cuvs" -type "string" "map1";
	setAttr ".dcc" -type "string" "Diffuse";
	setAttr ".covm[0]"  0 1 1;
	setAttr ".cdvm[0]"  0 1 1;
	setAttr ".ndt" 0;
createNode transform -n "AntennaStem";
	rename -uid "E6D05FA6-4A91-E39A-57CB-1388B9129DA0";
	setAttr ".t" -type "double3" 0 3.05 0.03 ;
createNode mesh -n "AntennaStemShape" -p "AntennaStem";
	rename -uid "AF92187C-438A-9C7C-5EB7-BEB54F562513";
	setAttr -k off ".v";
	setAttr ".vir" yes;
	setAttr ".vif" yes;
	setAttr ".uvst[0].uvsn" -type "string" "map1";
	setAttr ".cuvs" -type "string" "map1";
	setAttr ".dcc" -type "string" "Diffuse";
	setAttr ".covm[0]"  0 1 1;
	setAttr ".cdvm[0]"  0 1 1;
	setAttr ".ndt" 0;
createNode transform -n "ChestBadge";
	rename -uid "7E84B165-4E04-9247-FD81-BAA4419F15F9";
	setAttr ".t" -type "double3" 0 1.4 0.45 ;
createNode mesh -n "ChestBadgeShape" -p "ChestBadge";
	rename -uid "4D43B907-43C1-F40F-0118-F38B65C34F8E";
	setAttr -k off ".v";
	setAttr ".vir" yes;
	setAttr ".vif" yes;
	setAttr ".uvst[0].uvsn" -type "string" "map1";
	setAttr ".cuvs" -type "string" "map1";
	setAttr ".dcc" -type "string" "Diffuse";
	setAttr ".covm[0]"  0 1 1;
	setAttr ".cdvm[0]"  0 1 1;
	setAttr ".ndt" 0;
createNode transform -n "DemoGround";
	rename -uid "0669048F-47BC-5447-2FF2-42B5D1C4C80B";
createNode mesh -n "DemoGroundShape" -p "DemoGround";
	rename -uid "D609F920-40E8-D6BC-404F-4FA3D3CE7BA5";
	setAttr -k off ".v";
	setAttr ".vir" yes;
	setAttr ".vif" yes;
	setAttr ".uvst[0].uvsn" -type "string" "map1";
	setAttr ".cuvs" -type "string" "map1";
	setAttr ".dcc" -type "string" "Diffuse";
	setAttr ".covm[0]"  0 1 1;
	setAttr ".cdvm[0]"  0 1 1;
	setAttr ".ndt" 0;
createNode transform -n "ReaToonCamera1";
	rename -uid "7C2159F2-4937-B254-1E05-05AF62739BC4";
	setAttr ".t" -type "double3" 5.6 3.8 9.5 ;
	setAttr ".r" -type "double3" -11.781056184205919 30.518230678875252 1.361431937790197e-13 ;
createNode camera -n "ReaToonCameraShape1" -p "ReaToonCamera1";
	rename -uid "3D5E6675-4BAA-0EA4-603D-459D0DFC3731";
	setAttr -k off ".v";
	setAttr ".fl" 45;
	setAttr ".fcp" 30;
	setAttr ".imn" -type "string" "ReaToonCamera1";
	setAttr ".den" -type "string" "ReaToonCamera1_depth";
	setAttr ".man" -type "string" "ReaToonCamera1_mask";
createNode transform -n "DemoKeyLight";
	rename -uid "784521B7-48B5-7611-D3D6-65830E06F366";
	setAttr ".r" -type "double3" -40 -35 0 ;
createNode directionalLight -n "DemoKeyLightShape" -p "DemoKeyLight";
	rename -uid "3353F521-47D4-4181-80ED-50A455739B27";
	setAttr -k off ".v";
	setAttr ".in" 0.80000001192092896;
createNode lightLinker -s -n "lightLinker1";
	rename -uid "8A9C7F75-4079-0348-17AD-16BDE74DC8DB";
	setAttr -s 14 ".lnk";
	setAttr -s 14 ".slnk";
createNode displayLayerManager -n "layerManager";
	rename -uid "085B2AAC-4B70-971C-582F-DCA2589B09AF";
createNode displayLayer -n "defaultLayer";
	rename -uid "7DDDDAE8-46A8-9C59-DD7A-AAAC0EA48E19";
	setAttr ".ufem" -type "stringArray" 0  ;
createNode renderLayerManager -n "renderLayerManager";
	rename -uid "8EF4178E-4CDA-0E97-328D-36ABB7786E31";
createNode renderLayer -n "defaultRenderLayer";
	rename -uid "BCDB2894-4FBC-6E7C-5DED-95AECA462B3A";
	setAttr ".g" yes;
createNode polyCube -n "polyCube1";
	rename -uid "E22D5647-4DB5-C4CD-190B-AA81CBDE8DB0";
	setAttr ".w" 1.25;
	setAttr ".h" 1.2;
	setAttr ".d" 0.85;
createNode polyBevel3 -n "polyBevel1";
	rename -uid "56FB9E8E-45F1-F2AF-AD4B-B29FA0935886";
	setAttr ".uopa" yes;
	setAttr ".ics" -type "componentList" 1 "e[0:11]";
	setAttr ".ix" -type "matrix" 1 0 0 0 0 1 0 0 0 0 1 0 0 1.25 0 1;
	setAttr ".f" 0.12;
	setAttr ".sg" 2;
createNode rampShader -n "BodyTeal";
	rename -uid "2AAA3F20-4270-2179-2584-ECADEF78E10C";
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
	setAttr ".reaToonBaseColor" -type "float3" 0.1 0.60000002 0.58999997 ;
	setAttr ".reaToonShadowColor" -type "float3" 0.037999999 0.228 0.2242 ;
	setAttr ".reaToonHighlightColor" -type "float3" 0.505 0.77999997 0.77450001 ;
	setAttr -k on ".reaToonThreshold";
	setAttr -k on ".reaToonHighlightThreshold";
createNode shadingEngine -n "BodyTealSG";
	rename -uid "21485052-4FE5-A933-2F40-AF829E29F10A";
	setAttr ".ihi" 0;
	setAttr ".ro" yes;
createNode materialInfo -n "materialInfo1";
	rename -uid "894F0064-41EC-ED65-DB5D-F09C4EFA0CE4";
createNode polySphere -n "polySphere1";
	rename -uid "475448F2-47D7-8949-D966-138B1673C71C";
	setAttr ".sa" 32;
createNode rampShader -n "DemoHeadToon";
	rename -uid "2C98B030-4FA0-699E-9762-16A18E2B6FEE";
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
	setAttr ".reaToonBaseColor" -type "float3" 0.98000002 0.69 0.25 ;
	setAttr ".reaToonShadowColor" -type "float3" 0.37239999 0.2622 0.094999999 ;
	setAttr ".reaToonHighlightColor" -type "float3" 0.98900002 0.82950002 0.58749998 ;
	setAttr -k on ".reaToonThreshold";
	setAttr -k on ".reaToonHighlightThreshold";
createNode shadingEngine -n "DemoHeadToonSG";
	rename -uid "114D2C6B-43AE-3CF0-36D4-42BA2EDECEB8";
	setAttr ".ihi" 0;
	setAttr ".ro" yes;
createNode materialInfo -n "materialInfo2";
	rename -uid "0EDB5FC5-4336-F176-E864-2F88E804017E";
createNode polySphere -n "polySphere2";
	rename -uid "5932FFE8-4546-0AF0-04A7-84A8E7295FEA";
	setAttr ".sa" 32;
createNode rampShader -n "LeftEyeToon";
	rename -uid "3600DEEA-457B-3875-ED89-1F959073E5EA";
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
	setAttr ".reaToonBaseColor" -type "float3" 0.059999999 0.090000004 0.14 ;
	setAttr ".reaToonShadowColor" -type "float3" 0.0228 0.034200002 0.053199999 ;
	setAttr ".reaToonHighlightColor" -type "float3" 0.48300001 0.49950001 0.52700001 ;
	setAttr -k on ".reaToonThreshold";
	setAttr -k on ".reaToonHighlightThreshold";
createNode shadingEngine -n "LeftEyeToonSG";
	rename -uid "A141828A-4EEB-E4E2-B531-459FD8707BDA";
	setAttr ".ihi" 0;
	setAttr ".ro" yes;
createNode materialInfo -n "materialInfo3";
	rename -uid "CC977E8E-49FE-7E38-4745-168C3ACF2DBB";
createNode polySphere -n "polySphere3";
	rename -uid "8B73819C-442E-6F42-4B1A-ADA4F4E4095C";
	setAttr ".sa" 32;
createNode rampShader -n "RightEyeToon";
	rename -uid "13346BBA-4D04-A468-8B31-8CA62804DF69";
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
	setAttr ".reaToonBaseColor" -type "float3" 0.059999999 0.090000004 0.14 ;
	setAttr ".reaToonShadowColor" -type "float3" 0.0228 0.034200002 0.053199999 ;
	setAttr ".reaToonHighlightColor" -type "float3" 0.48300001 0.49950001 0.52700001 ;
	setAttr -k on ".reaToonThreshold";
	setAttr -k on ".reaToonHighlightThreshold";
createNode shadingEngine -n "RightEyeToonSG";
	rename -uid "9B191B8E-4AB2-644A-39A4-818D4CE88B62";
	setAttr ".ihi" 0;
	setAttr ".ro" yes;
createNode materialInfo -n "materialInfo4";
	rename -uid "8441F5C9-41FF-DF10-609D-78950FDF59B9";
createNode polySphere -n "polySphere4";
	rename -uid "AEBD22BF-4186-A1A1-B7BC-AB94F41FCC72";
	setAttr ".sa" 32;
createNode rampShader -n "LeftHandToon";
	rename -uid "275DA411-4E8C-4AAF-2C84-60A4BAA79122";
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
	setAttr ".reaToonBaseColor" -type "float3" 0.98000002 0.69 0.25 ;
	setAttr ".reaToonShadowColor" -type "float3" 0.37239999 0.2622 0.094999999 ;
	setAttr ".reaToonHighlightColor" -type "float3" 0.98900002 0.82950002 0.58749998 ;
	setAttr -k on ".reaToonThreshold";
	setAttr -k on ".reaToonHighlightThreshold";
createNode shadingEngine -n "LeftHandToonSG";
	rename -uid "D4D1D75C-4AB3-A02D-9FA7-13896B76E692";
	setAttr ".ihi" 0;
	setAttr ".ro" yes;
createNode materialInfo -n "materialInfo5";
	rename -uid "39D46DF8-4321-FAF9-3C50-91B07BC697B4";
createNode polySphere -n "polySphere5";
	rename -uid "4B8FD011-4C9B-EF01-80D5-8AB0ADE552BC";
	setAttr ".sa" 32;
createNode rampShader -n "RightHandToon";
	rename -uid "3ECDBCC4-4F4A-757B-6361-F9B26DEA6AB7";
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
	setAttr ".reaToonBaseColor" -type "float3" 0.98000002 0.69 0.25 ;
	setAttr ".reaToonShadowColor" -type "float3" 0.37239999 0.2622 0.094999999 ;
	setAttr ".reaToonHighlightColor" -type "float3" 0.98900002 0.82950002 0.58749998 ;
	setAttr -k on ".reaToonThreshold";
	setAttr -k on ".reaToonHighlightThreshold";
createNode shadingEngine -n "RightHandToonSG";
	rename -uid "190772AF-4D1E-74B8-9F1C-BEAD4A5B42AA";
	setAttr ".ihi" 0;
	setAttr ".ro" yes;
createNode materialInfo -n "materialInfo6";
	rename -uid "6FE639AA-4BB3-7103-6E91-3AA3CBEB0076";
createNode polySphere -n "polySphere6";
	rename -uid "355362A4-4E3A-F26A-A9CE-62A0C9D4CE86";
	setAttr ".sa" 32;
createNode rampShader -n "LeftFootToon";
	rename -uid "ED26ED4D-4CDF-551D-612B-A49667EACEDB";
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
	setAttr ".reaToonBaseColor" -type "float3" 0.12 0.28999999 0.38999999 ;
	setAttr ".reaToonShadowColor" -type "float3" 0.045600001 0.1102 0.14820001 ;
	setAttr ".reaToonHighlightColor" -type "float3" 0.51599997 0.60949999 0.6645 ;
	setAttr -k on ".reaToonThreshold";
	setAttr -k on ".reaToonHighlightThreshold";
createNode shadingEngine -n "LeftFootToonSG";
	rename -uid "7EEC2DD7-468E-5A79-2E60-F89FF1405295";
	setAttr ".ihi" 0;
	setAttr ".ro" yes;
createNode materialInfo -n "materialInfo7";
	rename -uid "2F71B13D-4E9A-22CF-2802-7C88697EE26D";
createNode polySphere -n "polySphere7";
	rename -uid "0D137E93-464D-36AE-D001-9B98F94F2FBA";
	setAttr ".sa" 32;
createNode rampShader -n "RightFootToon";
	rename -uid "D2EC2631-40AD-D67C-7966-C292EF3C41B7";
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
	setAttr ".reaToonBaseColor" -type "float3" 0.12 0.28999999 0.38999999 ;
	setAttr ".reaToonShadowColor" -type "float3" 0.045600001 0.1102 0.14820001 ;
	setAttr ".reaToonHighlightColor" -type "float3" 0.51599997 0.60949999 0.6645 ;
	setAttr -k on ".reaToonThreshold";
	setAttr -k on ".reaToonHighlightThreshold";
createNode shadingEngine -n "RightFootToonSG";
	rename -uid "6FEAEAC2-4EE8-021D-9BE7-F0842430F514";
	setAttr ".ihi" 0;
	setAttr ".ro" yes;
createNode materialInfo -n "materialInfo8";
	rename -uid "FD10E7A3-4BB2-A9EB-33E5-E4995D9AD023";
createNode polySphere -n "polySphere8";
	rename -uid "12F69DFB-47CE-50AE-79DE-3D94335F2B30";
	setAttr ".sa" 32;
createNode rampShader -n "AntennaToon";
	rename -uid "8803C660-42B4-8A5E-BAC4-08B5305B4519";
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
	setAttr ".reaToonBaseColor" -type "float3" 0.89999998 0.23999999 0.25999999 ;
	setAttr ".reaToonShadowColor" -type "float3" 0.34200001 0.091200002 0.098800004 ;
	setAttr ".reaToonHighlightColor" -type "float3" 0.94499999 0.58200002 0.59299999 ;
	setAttr -k on ".reaToonThreshold";
	setAttr -k on ".reaToonHighlightThreshold";
createNode shadingEngine -n "AntennaToonSG";
	rename -uid "3BE57A05-49F8-AD56-D608-4E92B5E69153";
	setAttr ".ihi" 0;
	setAttr ".ro" yes;
createNode materialInfo -n "materialInfo9";
	rename -uid "2F1D70F0-4C4E-AFAE-373C-7E84277A9F96";
createNode polyCylinder -n "polyCylinder1";
	rename -uid "BD943DA1-4CF5-A277-92F9-74A9CDB0B87B";
	setAttr ".r" 0.045;
	setAttr ".h" 0.35;
	setAttr ".sa" 12;
createNode rampShader -n "StemDark";
	rename -uid "20C985BC-4125-6ABC-8C46-E0A68033C9DA";
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
	setAttr ".reaToonBaseColor" -type "float3" 0.12 0.28999999 0.38999999 ;
	setAttr ".reaToonShadowColor" -type "float3" 0.045600001 0.1102 0.14820001 ;
	setAttr ".reaToonHighlightColor" -type "float3" 0.51599997 0.60949999 0.6645 ;
	setAttr -k on ".reaToonThreshold";
	setAttr -k on ".reaToonHighlightThreshold";
createNode shadingEngine -n "StemDarkSG";
	rename -uid "285840A2-4A65-4321-F030-F68B882646E9";
	setAttr ".ihi" 0;
	setAttr ".ro" yes;
createNode materialInfo -n "materialInfo10";
	rename -uid "3D5BEA99-4C72-111B-902B-68BE6B96EFB3";
createNode polyCube -n "polyCube2";
	rename -uid "4EF98DB6-4BDE-1BD0-18D5-71BC7B92E917";
	setAttr ".w" 0.45;
	setAttr ".h" 0.21;
	setAttr ".d" 0.04;
createNode rampShader -n "BadgeCream";
	rename -uid "DDB5B830-4B2C-9D61-A0FA-078F207D52B9";
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
	setAttr ".reaToonBaseColor" -type "float3" 0.94999999 0.93000001 0.79000002 ;
	setAttr ".reaToonShadowColor" -type "float3" 0.361 0.35339999 0.30019999 ;
	setAttr ".reaToonHighlightColor" -type "float3" 0.97250003 0.96149999 0.88450003 ;
	setAttr -k on ".reaToonThreshold";
	setAttr -k on ".reaToonHighlightThreshold";
createNode shadingEngine -n "BadgeCreamSG";
	rename -uid "234BB91F-4F8E-B1D7-16E0-E28EFDCC9609";
	setAttr ".ihi" 0;
	setAttr ".ro" yes;
createNode materialInfo -n "materialInfo11";
	rename -uid "A7BA2150-4342-EA21-B3C0-D98F1F3A5005";
createNode polyPlane -n "polyPlane1";
	rename -uid "1689FD42-418E-AAD5-85A0-03B4BE31876D";
	setAttr ".w" 5;
	setAttr ".h" 4;
	setAttr ".sw" 1;
	setAttr ".sh" 1;
createNode rampShader -n "GroundCream";
	rename -uid "370BA3A5-4090-A9A8-5A51-8C94671EC155";
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
	setAttr ".reaToonBaseColor" -type "float3" 0.88 0.88 0.82999998 ;
	setAttr ".reaToonShadowColor" -type "float3" 0.3344 0.3344 0.3154 ;
	setAttr ".reaToonHighlightColor" -type "float3" 0.93400002 0.93400002 0.90649998 ;
	setAttr -k on ".reaToonThreshold";
	setAttr -k on ".reaToonHighlightThreshold";
createNode shadingEngine -n "GroundCreamSG";
	rename -uid "52666015-41D7-5BC0-5B05-7F8CB4AE9654";
	setAttr ".ihi" 0;
	setAttr ".ro" yes;
createNode materialInfo -n "materialInfo12";
	rename -uid "E4E7FAEB-442C-664D-BD30-689228100F36";
createNode objectSet -n "HeroLines";
	rename -uid "612D8388-484F-2014-CBAA-83AC14A74636";
	addAttr -ci true -sn "reaToonKind" -ln "reaToonKind" -dt "string";
	addAttr -ci true -sn "reaToonOverrides" -ln "reaToonOverrides" -dt "string";
	setAttr ".ihi" 0;
	setAttr -s 2 ".dsm";
	setAttr ".reaToonKind" -type "string" "lineSet";
	setAttr ".reaToonOverrides" -type "string" "{\"line_width\": 1.6}";
createNode network -n "reaToonSettings";
	rename -uid "CF0ABEC8-4398-9A9F-67A8-3384D56A4F40";
	addAttr -ci true -sn "reaToonKind" -ln "reaToonKind" -dt "string";
	addAttr -ci true -sn "reaToonSettingsJson" -ln "reaToonSettingsJson" -dt "string";
	setAttr ".reaToonKind" -type "string" "settings";
	setAttr ".reaToonSettingsJson" -type "string" "{\"background\": [0.97, 0.97, 0.94], \"crease\": true, \"crease_angle\": 45, \"dash_length\": 0.0, \"depth_bias\": 0.002, \"distance_reduction\": 0.0, \"hard_edges\": true, \"height\": 480, \"hidden_color\": [0.5, 0.5, 0.6], \"hidden_lines\": false, \"line_color\": [0.055, 0.075, 0.1], \"line_width\": 1.35, \"material_boundaries\": true, \"open_edges\": true, \"outline\": true, \"seed\": 1, \"selected_edges\": true, \"supersample\": 2, \"taper\": 0.0, \"width\": 640, \"width_variation\": 0.0, \"wireframe\": false}";
createNode script -n "uiConfigurationScriptNode";
	rename -uid "4268BE67-47AA-2B0D-00B8-72A15A30B763";
	setAttr ".b" -type "string" "// Maya Mel UI Configuration File.\n// No UI generated in batch mode.\n";
	setAttr ".st" 3;
createNode script -n "sceneConfigurationScriptNode";
	rename -uid "9EE5F1DF-4DCB-83A6-6E7D-408227E886C6";
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
	setAttr -s 14 ".st";
select -ne :renderGlobalsList1;
select -ne :defaultShaderList1;
	setAttr -s 17 ".s";
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
connectAttr "polyBevel1.out" "DemoBodyShape.i";
connectAttr "polySphere1.out" "DemoHeadShape.i";
connectAttr "polySphere2.out" "LeftEyeShape.i";
connectAttr "polySphere3.out" "RightEyeShape.i";
connectAttr "polySphere4.out" "LeftHandShape.i";
connectAttr "polySphere5.out" "RightHandShape.i";
connectAttr "polySphere6.out" "LeftFootShape.i";
connectAttr "polySphere7.out" "RightFootShape.i";
connectAttr "polySphere8.out" "AntennaShape.i";
connectAttr "polyCylinder1.out" "AntennaStemShape.i";
connectAttr "polyCube2.out" "ChestBadgeShape.i";
connectAttr "polyPlane1.out" "DemoGroundShape.i";
relationship "link" ":lightLinker1" ":initialShadingGroup.message" ":defaultLightSet.message";
relationship "link" ":lightLinker1" ":initialParticleSE.message" ":defaultLightSet.message";
relationship "link" ":lightLinker1" "BodyTealSG.message" ":defaultLightSet.message";
relationship "link" ":lightLinker1" "DemoHeadToonSG.message" ":defaultLightSet.message";
relationship "link" ":lightLinker1" "LeftEyeToonSG.message" ":defaultLightSet.message";
relationship "link" ":lightLinker1" "RightEyeToonSG.message" ":defaultLightSet.message";
relationship "link" ":lightLinker1" "LeftHandToonSG.message" ":defaultLightSet.message";
relationship "link" ":lightLinker1" "RightHandToonSG.message" ":defaultLightSet.message";
relationship "link" ":lightLinker1" "LeftFootToonSG.message" ":defaultLightSet.message";
relationship "link" ":lightLinker1" "RightFootToonSG.message" ":defaultLightSet.message";
relationship "link" ":lightLinker1" "AntennaToonSG.message" ":defaultLightSet.message";
relationship "link" ":lightLinker1" "StemDarkSG.message" ":defaultLightSet.message";
relationship "link" ":lightLinker1" "BadgeCreamSG.message" ":defaultLightSet.message";
relationship "link" ":lightLinker1" "GroundCreamSG.message" ":defaultLightSet.message";
relationship "shadowLink" ":lightLinker1" ":initialShadingGroup.message" ":defaultLightSet.message";
relationship "shadowLink" ":lightLinker1" ":initialParticleSE.message" ":defaultLightSet.message";
relationship "shadowLink" ":lightLinker1" "BodyTealSG.message" ":defaultLightSet.message";
relationship "shadowLink" ":lightLinker1" "DemoHeadToonSG.message" ":defaultLightSet.message";
relationship "shadowLink" ":lightLinker1" "LeftEyeToonSG.message" ":defaultLightSet.message";
relationship "shadowLink" ":lightLinker1" "RightEyeToonSG.message" ":defaultLightSet.message";
relationship "shadowLink" ":lightLinker1" "LeftHandToonSG.message" ":defaultLightSet.message";
relationship "shadowLink" ":lightLinker1" "RightHandToonSG.message" ":defaultLightSet.message";
relationship "shadowLink" ":lightLinker1" "LeftFootToonSG.message" ":defaultLightSet.message";
relationship "shadowLink" ":lightLinker1" "RightFootToonSG.message" ":defaultLightSet.message";
relationship "shadowLink" ":lightLinker1" "AntennaToonSG.message" ":defaultLightSet.message";
relationship "shadowLink" ":lightLinker1" "StemDarkSG.message" ":defaultLightSet.message";
relationship "shadowLink" ":lightLinker1" "BadgeCreamSG.message" ":defaultLightSet.message";
relationship "shadowLink" ":lightLinker1" "GroundCreamSG.message" ":defaultLightSet.message";
connectAttr "layerManager.dli[0]" "defaultLayer.id";
connectAttr "renderLayerManager.rlmi[0]" "defaultRenderLayer.rlid";
connectAttr "polyCube1.out" "polyBevel1.ip";
connectAttr "DemoBodyShape.wm" "polyBevel1.mp";
connectAttr "BodyTeal.reaToonShadowColor" "BodyTeal.clr[0].clrc";
connectAttr "BodyTeal.reaToonBaseColor" "BodyTeal.clr[1].clrc";
connectAttr "BodyTeal.reaToonThreshold" "BodyTeal.clr[1].clrp";
connectAttr "BodyTeal.reaToonHighlightColor" "BodyTeal.clr[2].clrc";
connectAttr "BodyTeal.reaToonHighlightThreshold" "BodyTeal.clr[2].clrp";
connectAttr "BodyTeal.oc" "BodyTealSG.ss";
connectAttr "DemoBodyShape.iog" "BodyTealSG.dsm" -na;
connectAttr "BodyTealSG.msg" "materialInfo1.sg";
connectAttr "DemoHeadToon.reaToonShadowColor" "DemoHeadToon.clr[0].clrc";
connectAttr "DemoHeadToon.reaToonBaseColor" "DemoHeadToon.clr[1].clrc";
connectAttr "DemoHeadToon.reaToonThreshold" "DemoHeadToon.clr[1].clrp";
connectAttr "DemoHeadToon.reaToonHighlightColor" "DemoHeadToon.clr[2].clrc";
connectAttr "DemoHeadToon.reaToonHighlightThreshold" "DemoHeadToon.clr[2].clrp";
connectAttr "DemoHeadToon.oc" "DemoHeadToonSG.ss";
connectAttr "DemoHeadShape.iog" "DemoHeadToonSG.dsm" -na;
connectAttr "DemoHeadToonSG.msg" "materialInfo2.sg";
connectAttr "LeftEyeToon.reaToonShadowColor" "LeftEyeToon.clr[0].clrc";
connectAttr "LeftEyeToon.reaToonBaseColor" "LeftEyeToon.clr[1].clrc";
connectAttr "LeftEyeToon.reaToonThreshold" "LeftEyeToon.clr[1].clrp";
connectAttr "LeftEyeToon.reaToonHighlightColor" "LeftEyeToon.clr[2].clrc";
connectAttr "LeftEyeToon.reaToonHighlightThreshold" "LeftEyeToon.clr[2].clrp";
connectAttr "LeftEyeToon.oc" "LeftEyeToonSG.ss";
connectAttr "LeftEyeShape.iog" "LeftEyeToonSG.dsm" -na;
connectAttr "LeftEyeToonSG.msg" "materialInfo3.sg";
connectAttr "RightEyeToon.reaToonShadowColor" "RightEyeToon.clr[0].clrc";
connectAttr "RightEyeToon.reaToonBaseColor" "RightEyeToon.clr[1].clrc";
connectAttr "RightEyeToon.reaToonThreshold" "RightEyeToon.clr[1].clrp";
connectAttr "RightEyeToon.reaToonHighlightColor" "RightEyeToon.clr[2].clrc";
connectAttr "RightEyeToon.reaToonHighlightThreshold" "RightEyeToon.clr[2].clrp";
connectAttr "RightEyeToon.oc" "RightEyeToonSG.ss";
connectAttr "RightEyeShape.iog" "RightEyeToonSG.dsm" -na;
connectAttr "RightEyeToonSG.msg" "materialInfo4.sg";
connectAttr "LeftHandToon.reaToonShadowColor" "LeftHandToon.clr[0].clrc";
connectAttr "LeftHandToon.reaToonBaseColor" "LeftHandToon.clr[1].clrc";
connectAttr "LeftHandToon.reaToonThreshold" "LeftHandToon.clr[1].clrp";
connectAttr "LeftHandToon.reaToonHighlightColor" "LeftHandToon.clr[2].clrc";
connectAttr "LeftHandToon.reaToonHighlightThreshold" "LeftHandToon.clr[2].clrp";
connectAttr "LeftHandToon.oc" "LeftHandToonSG.ss";
connectAttr "LeftHandShape.iog" "LeftHandToonSG.dsm" -na;
connectAttr "LeftHandToonSG.msg" "materialInfo5.sg";
connectAttr "RightHandToon.reaToonShadowColor" "RightHandToon.clr[0].clrc";
connectAttr "RightHandToon.reaToonBaseColor" "RightHandToon.clr[1].clrc";
connectAttr "RightHandToon.reaToonThreshold" "RightHandToon.clr[1].clrp";
connectAttr "RightHandToon.reaToonHighlightColor" "RightHandToon.clr[2].clrc";
connectAttr "RightHandToon.reaToonHighlightThreshold" "RightHandToon.clr[2].clrp"
		;
connectAttr "RightHandToon.oc" "RightHandToonSG.ss";
connectAttr "RightHandShape.iog" "RightHandToonSG.dsm" -na;
connectAttr "RightHandToonSG.msg" "materialInfo6.sg";
connectAttr "LeftFootToon.reaToonShadowColor" "LeftFootToon.clr[0].clrc";
connectAttr "LeftFootToon.reaToonBaseColor" "LeftFootToon.clr[1].clrc";
connectAttr "LeftFootToon.reaToonThreshold" "LeftFootToon.clr[1].clrp";
connectAttr "LeftFootToon.reaToonHighlightColor" "LeftFootToon.clr[2].clrc";
connectAttr "LeftFootToon.reaToonHighlightThreshold" "LeftFootToon.clr[2].clrp";
connectAttr "LeftFootToon.oc" "LeftFootToonSG.ss";
connectAttr "LeftFootShape.iog" "LeftFootToonSG.dsm" -na;
connectAttr "LeftFootToonSG.msg" "materialInfo7.sg";
connectAttr "RightFootToon.reaToonShadowColor" "RightFootToon.clr[0].clrc";
connectAttr "RightFootToon.reaToonBaseColor" "RightFootToon.clr[1].clrc";
connectAttr "RightFootToon.reaToonThreshold" "RightFootToon.clr[1].clrp";
connectAttr "RightFootToon.reaToonHighlightColor" "RightFootToon.clr[2].clrc";
connectAttr "RightFootToon.reaToonHighlightThreshold" "RightFootToon.clr[2].clrp"
		;
connectAttr "RightFootToon.oc" "RightFootToonSG.ss";
connectAttr "RightFootShape.iog" "RightFootToonSG.dsm" -na;
connectAttr "RightFootToonSG.msg" "materialInfo8.sg";
connectAttr "AntennaToon.reaToonShadowColor" "AntennaToon.clr[0].clrc";
connectAttr "AntennaToon.reaToonBaseColor" "AntennaToon.clr[1].clrc";
connectAttr "AntennaToon.reaToonThreshold" "AntennaToon.clr[1].clrp";
connectAttr "AntennaToon.reaToonHighlightColor" "AntennaToon.clr[2].clrc";
connectAttr "AntennaToon.reaToonHighlightThreshold" "AntennaToon.clr[2].clrp";
connectAttr "AntennaToon.oc" "AntennaToonSG.ss";
connectAttr "AntennaShape.iog" "AntennaToonSG.dsm" -na;
connectAttr "AntennaToonSG.msg" "materialInfo9.sg";
connectAttr "StemDark.reaToonShadowColor" "StemDark.clr[0].clrc";
connectAttr "StemDark.reaToonBaseColor" "StemDark.clr[1].clrc";
connectAttr "StemDark.reaToonThreshold" "StemDark.clr[1].clrp";
connectAttr "StemDark.reaToonHighlightColor" "StemDark.clr[2].clrc";
connectAttr "StemDark.reaToonHighlightThreshold" "StemDark.clr[2].clrp";
connectAttr "StemDark.oc" "StemDarkSG.ss";
connectAttr "AntennaStemShape.iog" "StemDarkSG.dsm" -na;
connectAttr "StemDarkSG.msg" "materialInfo10.sg";
connectAttr "BadgeCream.reaToonShadowColor" "BadgeCream.clr[0].clrc";
connectAttr "BadgeCream.reaToonBaseColor" "BadgeCream.clr[1].clrc";
connectAttr "BadgeCream.reaToonThreshold" "BadgeCream.clr[1].clrp";
connectAttr "BadgeCream.reaToonHighlightColor" "BadgeCream.clr[2].clrc";
connectAttr "BadgeCream.reaToonHighlightThreshold" "BadgeCream.clr[2].clrp";
connectAttr "BadgeCream.oc" "BadgeCreamSG.ss";
connectAttr "ChestBadgeShape.iog" "BadgeCreamSG.dsm" -na;
connectAttr "BadgeCreamSG.msg" "materialInfo11.sg";
connectAttr "GroundCream.reaToonShadowColor" "GroundCream.clr[0].clrc";
connectAttr "GroundCream.reaToonBaseColor" "GroundCream.clr[1].clrc";
connectAttr "GroundCream.reaToonThreshold" "GroundCream.clr[1].clrp";
connectAttr "GroundCream.reaToonHighlightColor" "GroundCream.clr[2].clrc";
connectAttr "GroundCream.reaToonHighlightThreshold" "GroundCream.clr[2].clrp";
connectAttr "GroundCream.oc" "GroundCreamSG.ss";
connectAttr "DemoGroundShape.iog" "GroundCreamSG.dsm" -na;
connectAttr "GroundCreamSG.msg" "materialInfo12.sg";
connectAttr "DemoHead.iog" "HeroLines.dsm" -na;
connectAttr "DemoBody.iog" "HeroLines.dsm" -na;
connectAttr "BodyTealSG.pa" ":renderPartition.st" -na;
connectAttr "DemoHeadToonSG.pa" ":renderPartition.st" -na;
connectAttr "LeftEyeToonSG.pa" ":renderPartition.st" -na;
connectAttr "RightEyeToonSG.pa" ":renderPartition.st" -na;
connectAttr "LeftHandToonSG.pa" ":renderPartition.st" -na;
connectAttr "RightHandToonSG.pa" ":renderPartition.st" -na;
connectAttr "LeftFootToonSG.pa" ":renderPartition.st" -na;
connectAttr "RightFootToonSG.pa" ":renderPartition.st" -na;
connectAttr "AntennaToonSG.pa" ":renderPartition.st" -na;
connectAttr "StemDarkSG.pa" ":renderPartition.st" -na;
connectAttr "BadgeCreamSG.pa" ":renderPartition.st" -na;
connectAttr "GroundCreamSG.pa" ":renderPartition.st" -na;
connectAttr "BodyTeal.msg" ":defaultShaderList1.s" -na;
connectAttr "DemoHeadToon.msg" ":defaultShaderList1.s" -na;
connectAttr "LeftEyeToon.msg" ":defaultShaderList1.s" -na;
connectAttr "RightEyeToon.msg" ":defaultShaderList1.s" -na;
connectAttr "LeftHandToon.msg" ":defaultShaderList1.s" -na;
connectAttr "RightHandToon.msg" ":defaultShaderList1.s" -na;
connectAttr "LeftFootToon.msg" ":defaultShaderList1.s" -na;
connectAttr "RightFootToon.msg" ":defaultShaderList1.s" -na;
connectAttr "AntennaToon.msg" ":defaultShaderList1.s" -na;
connectAttr "StemDark.msg" ":defaultShaderList1.s" -na;
connectAttr "BadgeCream.msg" ":defaultShaderList1.s" -na;
connectAttr "GroundCream.msg" ":defaultShaderList1.s" -na;
connectAttr "defaultRenderLayer.msg" ":defaultRenderingList1.r" -na;
connectAttr "DemoKeyLightShape.ltd" ":lightList1.l" -na;
connectAttr "DemoKeyLight.iog" ":defaultLightSet.dsm" -na;
dataStructure -fmt "raw" -as "name=externalContentTable:string=node:string=key:string=upath:uint32=upathcrc:string=rpath:string=roles";
applyMetadata -fmt "raw" -v "channel\nname externalContentTable\nstream\nname v1.0\nindexType numeric\nstructure externalContentTable\n0\n\"|DemoKeyLight|DemoKeyLightShape\" \"dmapName\" \"depthmap\" 2097411553 \"\" \"sourceImages\"\nendStream\nendChannel\nendAssociations\n" 
		-scn;
// End of ReaToon_Demo.ma
