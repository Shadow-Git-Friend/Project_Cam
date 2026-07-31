This CVPR paper is the Open Access version, provided by the Computer Vision Foundation. Except for this watermark, it is identical to the accepted version; the final published version of the proceedings is available on IEEE Xplore. 

## **AiOS: All-in-One-Stage Expressive Human Pose and Shape Estimation** 

Qingping Sun[*] _[,]_[1] _[,]_[2] , Yanjun Wang _[∗][,]_[1] , Ailing Zeng[3] , Wanqi Yin[1] , Chen Wei[1] , Wenjia Wang[5] , Haiyi Mei[1] , Chi-Sing Leung[2] , Ziwei Liu[4] , Lei Yang[1] _[,]_[5] , Zhongang Cai[†] _[,]_[1] _[,]_[4] _[,]_[5] 1 SenseTime Research 2 City University of Hong Kong 3 International Digital Economy Academy (IDEA) 4 S-Lab, Nanyang Technological University 5 Shanghai AI Laboratory _∗_ Equal Contributions, _†_ Corresponding Author https://ttxskk.github.io/AiOS/ 

**==> picture [413 x 66] intentionally omitted <==**

**----- Start of picture text -----**<br>
ℳ!"#$<br>ℳ )"* ' Merge  ℳ<br>ℳ%&'(<br>(a) Top-Down, Multi-Stage (b) Top-Down, One-Stage (c) Our All-in-One-Stage Method<br>Encoder Decoder<br>**----- End of picture text -----**<br>


Figure 1. A comparison of existing methods in EHPS. (a) Top-down, multi-stage methods typically use detectors to detect humans, then use different networks to regress body parts on cropped images. (b) Top-down, one-stage methods use only one network for regression but still require detectors and rely on the cropped image. (c) Our all-in-one-stage pipeline, end-to-end human detection, and regression on full frame. 

## **Abstract** 

_Expressive human pose and shape estimation (a.k.a. 3D whole-body mesh recovery) involves the human body, hand, and expression estimation. Most existing methods have tackled this task in a two-stage manner, first detecting the human body part with an off-the-shelf detection model and then inferring the different human body parts individually. Despite the impressive results achieved, these methods suffer from 1) loss of valuable contextual information via cropping, 2) introducing distractions, and 3) lacking inter-association among different persons and body parts, inevitably causing performance degradation, especially for crowded scenes. To address these issues, we introduce a novel all-in-one-stage framework, AiOS, for multiple expressive human pose and shape recovery without an additional human detection step. Specifically, our method is built upon DETR, which treats multi-person whole-body mesh recovery task as a progressive set prediction problem with various sequential detection. We devise the decoder tokens and extend them to our task. Specifically, we first employ a human token to probe a human location in the image and encode global features for each instance, which provides a coarse location for the later transformer block. Then, we introduce a joint-related token_ 

_to probe the human joint in the image and encoder a finegrained local feature, which collaborates with the global feature to regress the whole-body mesh. This straightforward but effective model outperforms previous state-of-theart methods by a 9% reduction in NMVE on AGORA, a 30% reduction in PVE on EHF, a 10% reduction in PVE on ARCTIC, and a 3% reduction in PVE on EgoBody._ 

## **1. Introduction** 

Expressive human pose and shape estimation (EHPS)[1] is a rapidly developing area. It plays an important role in human understanding and has broad applications in the animation, gaming, and streaming industries. Unlike human pose and shape estimation (HPS), which focuses solely on the human body, EHPS is designed to jointly estimate human body poses, hand gestures, and facial expressions from the image. 

In mainstream studies, the common approaches involve utilizing parametric human models, such as SMPL-X [30], to represent the articulated mesh model of a human and to regress the parameters for each body part. Drawing from research experience in single-part estimation, such as body 

> 1EHPS is used interchangeably with 3D whole-body human mesh recovery in this work 

1834 

pose and shape estimation [8, 13–15, 19, 20, 34, 39, 40, 51], existing methods [3, 7, 11, 18, 26, 27, 31] employ a multistage paradigm. As shown in Fig. 1a), the process begins by cropping the body parts using bounding boxes detected either by off-the-shelf detection models or provided via ground truth annotations. Following this, distinct models are utilized for the separate reconstruction of each individual body part. 

Obviously, this design compromises both complexity and accuracy. The images are processed multiple times with each model. The separate parts model blocks the inter-part, interhuman connection and brings inconsistent poses and unnatural artifacts at the connected joints. Recently, OSX [21] and SMPLer-X [3] discard part experts and regress the model in a holistic manner, which alleviates the artifacts. Their paradigm can be abstract to Fig. 1b), however, they still need to be given a bounding box to crop the image. While their benchmarks show promising results, the accurate ground truth bounding boxes are not attainable in real-world scenarios. RoboSMPLX [27] has demonstrated that the performance drops significantly under noisy boxes. Moreover, CLIFF [20] points out that the cropping operation discards the location information, which degrades the performance. 

A direct solution to address the challenges posed by the multi-stage paradigm is to utilize a one-stage framework that directly recovers EHPS from the entire image without requiring additional boxes for cropping. However, current one-stage methods [35–37] are proposed for HPS. Both of them use a body center heatmap and mesh parameter map to represent the potential human location and corresponding features. Relying solely on these human-centered global features is insufficient for achieving accurate part-wise regression. Although numerous two-stage HPS methods [14, 47] that extract local features in various ways, it is non-trivial to extend to a one-stage model, as most of the representations, like part-attention maps, are designed for a single person. 

In order to tackle the above challenges, we have proposed the first All-in-One-Stage (AiOS) EHPS method. This novel approach is capable of predicting every individual present in an image solely based on a single image input without any additional requirements. Inspired by the achievement of DETR-based [5] methods in various vision tasks [41, 42, 46, 48, 54], we designed our pipeline in a DETR [5] style with image feature encoder and various location-aware decoders. We tailored different queries and association strategies to progressively guide the decoder to perceive global and local human features from the entire image. 

Three key design features distinguish the AiOS model. **First** , it is built upon DETR structure, with a CNN backbone, transformer encoders, and decoders, and progressively detects human and decodes person features in an end-to-end manner. **Second** , we introduced the "Human-as-Tokens" design, where humans are conceptualized as a collection of box tokens and joint tokens. With different supervision and loca- 

tion cues, these tokens aggregate both global and local feature representations with cross-attention for enhanced model accuracy in diverse scenarios. **Third** , using self-attention and cross-attention mechanisms in our model allows for an in-depth analysis of inter-human and intra-human relationships, enhancing performance in crowded and occlusionheavy environments. 

Extensive experiments show that our proposed model has overpass state-of-the-art (SOTA) methods that utilize ground truth bounding boxes and also SOTA methods when the bounding box is not given. Further, our bounding box is accurate enough to improve the other two-stage methods on the AGORA benchmark. 

In summary, our contributions are i) The first one-stage method for EHPS that eliminates the need for extra detection networks; ii) A unified framework to integrate local and global features for whole-body regression; iii) SOTA performance on mainstream benchmarks without ground truth bounding boxes. 

## **2. Related Work** 

## **2.1. Expressive Human Mesh Recovery Methods** 

EHPS focuses on reconstructing the mesh of the human body, hands, and face from monocular images. Pioneering research in this domain introduced whole-body parametric models such as SMPL-X [30]. With advancements in regression techniques for the human body, hands, and face, early studies adopted multi-stage solutions [11, 26, 29, 31]. They independently recover body pose, hand pose, and facial expressions from cropped images before integration. However, these multi-stage methods often produce artifacts at joint intersections and present complex network designs. 

Given the recent surge in whole-body datasets [1, 2, 4, 28, 43], many approaches have transitioned to a holistic paradigm. OSX [21] presents a groundbreaking one-stage method, eliminating part-specific experts and cropped image regression. SMPLer-X [3] further amplifies one-stage methods utilizing large vision models and extensive datasets. However, they still rely on bounding boxes for image cropping. Despite their precision with ground truth bounding boxes, performance degrades under detected boxes [27]. 

## **2.2. One-Stage Human Mesh Recovery Methods** 

Most of the existing HPS methods [6, 8, 13, 16, 22, 39, 44, 45, 47] are multi-staged. Although these methods preserve relatively high-resolution images and generally have higher accuracy, they neglect other information in the full frame, including inter-person occlusions and individual positions [20]. To address these limitations, ROMP [35] first proposed to recover humans from an entire frame. It locates the human locations from a body center heatmap and indexes the corresponding features from the feature map to regress all human 

1835 

meshes. Furthermore, BEV [37] extends the 2D heatmap to 3D by incorporating a bird-eye-view. It enables the model to discern 3D relative positions within the frame. TRACE [36] further achieved simultaneously tracking humans and predicting camera motions with added motion maps. However, these center-map-based methods often distill the human into a single vector on the feature map and recover the human pose and shape based on this global feature. We reckon that this representation is insufficient for the EHPS task, particularly given that hand pose and expression require more fine-grind local features for accurate regression. 

## **3. Method** 

## **3.1. Motivation** 

For EHPS, using cropped images presents significant problems. The cropping discards the location information [20], and inaccurate bounding boxes may lead to missing body parts, negatively impacting performance. In crowded scenes, cropping struggles to distinguish individual humans, with parts from others intruding into the frame, leading to errors in human part detection and regression. Especially when people overlap significantly, the model struggles to differentiate them due to unclear bounding boxes. Furthermore, the detectors used are typically trained on general object detection datasets and are not specifically designed for human detection, adding to these difficulties. 

To tackle these problems, we introduced the AiOS, the first fully end-to-end network for EHPS. Abandoning the uncertain assumption of box-as-subject, our model leverages feature tokens and position queries for more precise human localization. We’ve developed a cohesive approach that combines global and local feature representations for accurate regression. To handle crowded scenarios and enhance the separation of human figures, our model employs attention mechanisms to establish intricate relationships between different body parts and between multiple individuals. 

location and extract global features of the body; 2) refine body location, extract body local features, localize coarse hands and face locations and extract global features of the hands and face; 3) refine hand and face location, extract local features for whole body. 

**Backbone.** AiOS utilizes the ResNet-50 [12] to extract a multi-scale feature maps _Fimg_ , which provide features from detailed to holistic. 

**Encoder.** As our task needs more than local associations, we utilize a standard transformer encoder [38] for long-distance relations. To transform the CNN-based feature map into a transformer-compatible feature vector, we flatten the multilayer feature maps along their spatial dimensions and concatenate them. The flattened feature is added with position encodings _PE ∈_ R _[M][×][D]_ to derive the image feature token _Timg ∈_ R _[M][×][D]_ , where _M_ represents the total length of the image feature token. We fed _Timg_ a transformer encoder, which produces the refined image feature tokens _Timg′_[, serv-] ing as a reference for cross-attention in the decoder. Utilizing _T ′ img_[, a feed-forward network (FFN) is applied to classify] each token as a human token. Following the approach in DINO [49] and ED-Pose [42], we filter based on the classification score and retain the top _Mh_ = 900 tokens. These tokens serve as candidate human body localization tokens _Tbody ∈_ R _[M][h][×][D]_ , and they also function as the input for the subsequent decoders. 

**Generic Decoder.** Similar to PETR [33] and ED-Pose [42], which extend the deformable decoder [53] to 2D human body-only pose estimation, AiOS extends the deformable decoderthree inputs, image content tokensto 3D whole-body mesh recovery. _Timg′[∈]_[R] It _[M]_ mainly _[×][D]_[, object] has content tokens _T ∈_ R _[M][h][×][D]_ and object position queries _Q ∈_ R _[M][h][×]_[4] . Utilizing this decoder, our model can automatically probe the suitable global and local features around the body parts for each human conditioned by various queries. We will introduce our key decoder designs in the following sections. 

## **3.4. Naive AiOS** 

## **3.2. Preliminaries** 

**SMPL-X.** We use 3D parametric model SMPL-X [30] to study EHPS. It utilizes a set of parameters to model body, face, and hands geometries. Specifically, our model estimates pose parameters _θ ∈_ R[53] _[×]_[3] , which include body poses _θbody ∈_ R[22] _[×]_[3] , left hand poses _θlhand ∈_ R[15] _[×]_[3] , right hand poses _θrhand ∈_ R[15] _[×]_[3] , and jaw poses _θjaw ∈_ R[1] _[×]_[3] . Additionally, it estimates shape parameters _β ∈_ R[10] , and facial expression parameters _ψ ∈_ R[10] . We use the joint regressor _J_ to obtain the 3D joint from the parameters by _J_ ( _M_ ( _β, θ, ψ_ )), where _M_ is the SMPL-X function. 

## **3.3. Overview** 

AiOS includes the backbone and transformer encoderdecoder structures. It has three steps, 1) localize coarse body 

Drawing inspiration from ROMP [35], we extend the DETR structure [5] to EHPS and progressively regress SMPL-X parameters. Specifically, we follow DAB-DETR [24] and introduce the location queries to probe the body, face, and handsrelated features, guided by bounding boxes ( _x, y, w, h_ ), that considers both the location and size of each body part boxes. The model first extracts features related to the body using body box location queries and refines them through the bodylocation decoder. Subsequently, they are expanded to include hands and face queries and leverage the whole-body-location decoder to extract whole-body features. 

**Body-location Decoder.** The first two decoders are bodycentric, and the input object content tokens _T_ are the body location tokens _Tbl_ . We derive body location query _Qbl_ with FFN from the corresponding _Tbl_ . The decoder first 

1836 

**==> picture [482 x 119] intentionally omitted <==**

**----- Start of picture text -----**<br>
𝑇%& 𝑇)& 𝑇*& 𝑇+<br>U0)0 t Body Localization Body Refinement Whole-body Refinement<br>𝑃𝐸<br>𝑇!"# … 𝑇%& … 𝑄%& 𝑇%( … 𝑄%& 𝑇'( … 𝑄'(<br>𝐹 Sam !"# Encoder Filter 𝑇!"#$ (00) Body LocationDecoder Filter &  CooL 𝑇!"#$ Bod RefinementDecoder Expand eae 𝑇!"#$ Whole-body RefinementDecoder<br>Expand<br>= a So<br>𝑇!"#$ … ne 𝑇%& … 𝑄%& 𝑇%( … 𝑄%& nine 𝑇'( … 𝑄'(<br>“1 J ou.<br>CNN Body  Body  Body  Body  Body  Body, Face, Body, Face, Body, Face, Body, Face,<br>Class Class Box Param Joint Hands Box Hands Param Hands Joint Hands Box<br>[\ ()<br>**----- End of picture text -----**<br>


Figure 2. **Pipeline overview** . AiOS performs human localization and SMPL-X estimation in a progressive manner. It is composed of (1) the body localization stage that predicts coarse human location; (2) the Body refinement stage that refines body features and produces face and hand locations; (3) the Whole-body Refinement stage that refines whole-body features and regress SMPL-X parameters. 

associates the body location tokens and updates them by the self-attentiontokens _Timg′_[as] mechanism.[the][value][and] Then,[the] the[updated] decoder[body] takes[location] image tokens as the query for cross-attention, and the _Qbl_ acts as an indicator, which is used to aggregate the information focusing on the corresponding body area. After that, the body location tokens _Tbl_ and body location queries _Qbl_ are refined with the decoder. 

We estimate the body bounding box with an FFN from _Tbl_ , which is supervised by _Lbox_ . This supervision makes sure the tokens aggregate global information of the human. Similar to the encoder, we classify the output _Tbl_ with an FFN on whether it is a token representing a human. The classification results from _Tbl_ are supervised with classification loss _Lcls_ . At the end of the second decoder, we downsample the body tokens again to _Mb_ = 100 to further distill potential human tokens and lower the computational complexity. 

**Whole-body-location Decoder.** The latter four decoders of naive AiOS jointly consider whole-body information and their association. With the body location tokens from the previous step, we expand them to hands and face location tokens with learnable embedding. We first broadcast the given embedding _Ebl ∈_ R _[D]_ and add it to the body location token _Tbl ∈_ R _[M][b][×][D]_ . After that, we obtained hand location tokens _Tlhl_ , _Trhl_ , and face location tokens _Tfl_ , which have the same shape as _Tbl_ . Then we concat them into a whole-body token _Tfull_ = [ _Tbl, Tlhl, Trhl, Tfl_ ]. Similarly, the whole-body location queries _Qfull_ are expanded from _Qbl_ with learnable embeddings. 

The decoders use a self-attention module to explore interpart and inter-human relations and then extract each part’s features around their bounding boxes with a conditioned 

cross-attention module. We utilize an attention mask to ensure that the bounding boxes for each person’s hands and face are associated only with their own and others’ body bounding boxes. As our model is already capable of recognizing each person’s body in the first two stages, this specific attention mechanism allows for more accurate identification of body parts in crowded scenes. We provide an illustration of the attention mechanism in the Supplementary Material. 

We regress body bounding boxes from _Tbl_ , face boxes from _Tfl_ and hand boxes from _Trhl_ , _Tlhl_ , and supervise them with _Lbox_ . We regress different part’s parameters from the refined whole body _Tfull_ tokens. The parameters are supervised with SMPL-X loss _Lsmplx_ , which includes parameter loss _Lparam_ , 3d keypoints loss _Lkp_ 3 _d_ , and the 2d keypoints reprojection loss _Lkp_ 2 _d_ . 

## **3.5. AiOS** 

Previous methods [35, 37] have shown that regressing multiperson body meshes from global features alone can achieve impressive results, but in EHPS, relying on global information alone is insufficient. The model should also consider local information to obtain a detailed context of the wholebody regression. Therefore, to elevate the model’s ability, we introduce joint-related tokens and their corresponding queries to our model. Combined with location tokens, the AiOS expresses human context in multilevel. We will further regress the SMPL-X parameter on this well-rounded feature group. Specifically, we adopt a progressive detection and decoding strategy. The first two layers are body-location decoders same as our naive design, which outputs coarse human location. Further, two layers of body-refinement decoders utilize body joint tokens to enrich local body features 

1837 

and estimate rough hand and face location simultaneously on the basis of human location. At last, two layers of wholebody-refinement decoders extract whole-body local features with extra hands and face joint tokens. 

**Body-refinement Decoder.** This decoder is built on bodylocation decoders in naive AiOS. In detail, we expand body joints tokens, hands location tokens, and face location tokens. We adopt the learnable-embedding _Ebj ∈_ R[17] _[×][D]_ to expand body joint tokens _Tbj ∈_ R _[M][b][×]_[17] _[×][D]_ from box location tokens, and then we obtain detailed body token set _Tbd_ = [ _Tbl, Tbj, Tlhl, Trhl, Tfl_ ]. Note that we use an attention mask to limit the joint attention within its subject as inter-joint attention among different subjects brings no incremental but much higher computation complexity. 

The _Tbd_ are refined with layers of decoders. Within each layer, similar to naive AiOS, we regress bounding boxes of body parts from their location tokens and supervise them with _Lbox_ . Further, we regress body joint location from _Tbj_ and supervise them with _Lj_ 2 _d_ , helping these joint tokens learn the local human features. Different from Naive AiOS, in this stage, we regress SMPL-X body parameters based on _Tbl_ , _Tbj_ . We use _Lsmplx_ to supervise the body parameter, helping to refine the body-related tokens representing more accurate body features. 

**Whole-body-refinement Decoder.** This decoder further expands the face and hand joint tokens. Similarly, we use embedding _Elhj_ , _Erhj_ , and _Efj_ to expand _Tlhl_ , _Trhl_ , and _Tfl_ to _Tlhj_ , _Trhj_ , and _Tfj_ , respectively. At this stage, the model forms the complete tokens that represent a human _Twd_ = [ _Tbl, Tbj, Tlhl, Tlhj, Trhl, Trhj, Tfl, Tfj_ ]. 

Based on _Twd_ , we utilize FFN to regress box location from _Tbl, Tlhl, Trhl, Tfl_ and supervised with _Lbox_ . We also regress whole-body joint location from _Tbj_ , _Tlhj_ , _Trhj_ , and _Tfj_ , and supervise them with _Lj_ 2 _d_ . Finally, we estimate SMPL-X body, hands, and face parameters from body, hand, and face-related tokens, respectively, and supervise wholebody parameters with _Lsmplx_ . 

**Overall Loss Functions.** The overall loss function is the sum of all the losses at each stage. Please refer to the Supplementary Material for the details. 

## **4. Experiment** 

## **4.1. Experimental Setup** 

Due to the page limit, we put the detailed experiment setup, implementation, and partial quantitative and qualitative comparison with SOTA methods in the Supplementary Material. **Datasets.** AiOS is trained on the multi-person datasets AGORA [28], BEDLAM [1], and COCO [23], and singleperson datasets UBody [21], ARCTIC [9], and EgoBody [52]. We evaluate it on AGORA, UBody, EHF [30], ARCTIC [9], Egobody [52], and BEDLAM [1]. **Implementation.** The training is conducted on 16 V100 

GPUs, with a total batch size of 32. We first train our model for 60 epochs on AGORA, BEDLAM, and COCO. We finetune it for 50 epochs on all train datasets. 

**Evaluation metrics.** Following the previous EHPS methods [3, 21, 26], we report Procrustes Aligned per-vertex position error (PA-MPVPE) and the mean per-vertex position error (MPVPE) across all benchmarks. In AGORA Leaderboard, we report mean vertex error (MVE), mean per-joint position error (MPJPE) for pure reconstruction accuracy; F Score, precision, recall for detection accuracy; Normalized mean vertex error (NMVE) and normalized mean joint error (NMJE) that considered regression accuracy with detection accuracy. All metrics are reported in millimeters (mm). 

## **4.2. Quantitative comparison with SOTA** 

In Table 1, we compare AiOS with the SOTA methods on the AGORA test set. The results are provided by the leaderboard[2] with their bounding boxes on the upper part of the table. We also feed our estimated bounding boxes to OSX [21] and SMPLer-X [3] on the lower part, which helps to verify our model’s localization quality. 

For a fair comparison with the SOTA methods, we utilize a threshold of 0.5 to filter the detected samples with lower confidence, which generally have severe occlusions. As shown on the upper part of Table 1, our model’s NMVE and NMJE greatly surpass the current SOTA method SMPLer-X. This observation proves that our one-stage pipeline achieves the best overall quality, combining localization and reconstruction. In terms of pure reconstruction quality, our model also achieves SOTA performance with a relatively accurate detection result on MVE and MPJPE. While BEDLAM [1] excels in face and hand reconstruction, its recall performance is comparatively low, omitting some instances for evaluation. 

On the lower-part comparison, we lower the detection threshold to 0.3, which has higher recall than any current results, allowing more hard cases to be detected. We feed the same bounding boxes to the OSX and SMPLer-X, and their performance on whole-body MVE improves compared with the results reported in the original paper (122.8 to 121.3 for OSX, 99.7 to 98.3 for SMPLer-X) even with a higher recall. This indicates that improvement is achieved not by filtering out hard cases but by providing high-quality bounding boxes. This finding proves that the current two-stage method is sensitive to bounding box quality, and using the ground truth box to crop images in other benchmarks is biased from real use cases. Notably, under this bounding box setting, AiOS is still much higher than the current SOTA OSX and comparable with the foundation model SMPLer-X L20. 

As the first one-stage method in EHPS, we cannot find relevant one-stage methods for a fair comparison. Therefore, similar to H4W [26], we compare the results of our body part with existing body-only methods, which can be broadly 

> 2https://agora-evaluation.is.tuebingen.mpg.de/ 

1838 

|Methods<br>F Score_↑_<br>Precision_↑_<br>Recall_↑_|NMVE_↓_(_mm_)<br>All<br>Body|NMJE_↓_(_mm_)<br>All<br>Body|MVE_↓_(_mm_)<br>All<br>Body<br>Face<br>LHand<br>RHand|MPJPE_↓_(_mm_)<br>All<br>Body<br>Face<br>LHand<br>RHhand|
|---|---|---|---|---|
|BEDLAM [1]<br>0.73<br>0.98<br>0.59<br>H4W [26]_†_<br>0.94<br>0.96<br>0.92<br>BEDLAM [1]_†_<br>0.73<br>0.98<br>0.59<br>PyMaF-X [50]_†_<br>0.89<br>0.90<br>0.89<br>OSX [21] _∗_<br>0.94<br>0.96<br>0.93<br>HybrIK-X [18]<br>0.93<br>0.95<br>0.92<br>SMPLer-X [3]<br>0.93<br>0.96<br>0.90<br>SMPLer-X [3]_†_<br>0.93<br>0.96<br>0.90<br>Native AiOS<br>0.93<br>0.98<br>0.89<br>AiOS<br>0.94<br>0.98<br>0.90|179.5<br>132.2<br>144.1<br>96.0<br>142.2<br>102.1<br>141.2<br>94.4<br>130.6<br>85.3<br>120.5<br>73.7<br>133.1<br>88.1<br>107.2<br>68.3<br>105.7<br>66.5<br>97.8<br>61.3|177.5<br>131.4<br>141.1<br>92.7<br>141.0<br>101.8<br>140.0<br>93.5<br>127.6<br>83.3<br>115.7<br>72.3<br>128.9<br>84.6<br>104.1<br>66.3<br>103.9<br>65.8<br>96.0<br>60.7|131.0<br>96.5<br>25.8<br>38.8<br>39.0<br>135.5<br>90.2<br>41.6<br>46.3<br>48.1<br>103.8<br>74.5<br>23.1<br>31.7<br>33.2<br>125.7<br>84.0<br>35.0<br>44.6<br>45.6<br>122.8<br>80.2<br>36.2<br>45.4<br>46.1<br>112.1<br>68.5<br>37.0<br>46.7<br>47.0<br>123.8<br>81.9<br>37.4<br>43.6<br>44.8<br>99.7<br>63.5<br>29.9<br>39.1<br>39.5<br>98.3<br>61.8<br>27.2<br>40.7<br>41.7<br>91.9<br>57.6<br>24.6<br>38.7<br>39.6|129.6<br>95.9<br>27.8<br>36.6<br>36.7<br>132.6<br>87.1<br>46.1<br>44.3<br>46.2<br>102.9<br>74.3<br>24.7<br>29.9<br>31.3<br>124.6<br>83.2<br>37.9<br>42.5<br>43.7<br>119.9<br>78.3<br>37.9<br>43.0<br>43.9<br>107.6<br>67.2<br>38.5<br>41.2<br>41.4<br>119.9<br>78.7<br>39.5<br>41.4<br>44.8<br>96.8<br>61.7<br>31.4<br>36.7<br>37.2<br>96.6<br>61.2<br>28.4<br>38.4<br>39.4<br>90.2<br>57.1<br>25.7<br>36.4<br>37.3|
|OSX [21]_∗⋄_<br>0.96<br>0.97<br>0.95<br>SMPLer-X [3]_†⋄_<br>0.96<br>0.97<br>0.95<br>AiOS<br>0.96<br>0.97<br>0.95|126.4<br>81.8<br>102.4<br>63.8<br>103.0<br>63.5|123.4<br>80.0<br>99.5<br>62.1<br>100.8<br>62.6|121.3<br>78.5<br>36.1<br>45.9<br>46.3<br>98.3<br>61.2<br>30.3<br>40.4<br>40.7<br>98.9<br>61.0<br>27.7<br>42.5<br>43.4|118.5<br>76.8<br>37.6<br>43.5<br>44.0<br>95.5<br>59.6<br>31.7<br>37.9<br>38.2<br>96.8<br>60.1<br>29.2<br>40.1<br>40.9|



Table 1. **AGORA SMPL-X test set.** _†_ denotes the methods finetuned on the AGORA training set. _∗_ denotes the methods trained on the AGORA training set only. _⋄_ denotes the methods that use the AiOS’s bounding box to crop the image. The best results are colored with red, and the second-best results are colored with blue for the upper and lower parts of the table, respectively. 

|Methods<br>F1-score_↑_<br>Precision_↑_<br>Recall_↑_<br>NMVE_↓_<br>NMJE_↓_<br>MVE_↓_<br>MPJPE_↓_|Methods<br>F1-score_↑_<br>Precision_↑_<br>Recall_↑_<br>NMVE_↓_<br>NMJE_↓_<br>MVE_↓_<br>MPJPE_↓_|Methods<br>F1-score_↑_<br>Precision_↑_<br>Recall_↑_<br>NMVE_↓_<br>NMJE_↓_<br>MVE_↓_<br>MPJPE_↓_|
|---|---|---|
|||Top-down Methods|
|HMR [13]<br>PyMAF [51]<br>PARE [14]<br>H4W [26]_†_<br>CLIFF [20]_†_<br>HybrIK [19]_†_<br>ProPose [10]_†_<br>PLIKS [32]_†_<br>NIKI [17]_†_|0.80<br>0.84<br>0.84<br>0.94<br>0.91<br>0.91<br>0.90<br>0.94<br>0.91|0.93<br>0.70<br>217.0<br>226.0<br>173.6<br>180.5<br>0.86<br>0.82<br>200.2<br>207.4<br>168.2<br>174.2<br>0.96<br>0.75<br>167.7<br>174.0<br>140.9<br>146.2<br>0.96<br>0.93<br>90.2<br>95.5<br>84.8<br>89.8<br>0.96<br>0.87<br>83.5<br>89.0<br>76.0<br>81.0<br>0.92<br>0.90<br>81.2<br>84.6<br>73.9<br>77.0<br>0.91<br>0.89<br>78.8<br>82.7<br>70.9<br>74.4<br>0.95<br>0.93<br>71.6<br>76.1<br>67.3<br>71.5<br>0.92<br>0.90<br>70.2<br>74.0<br>63.9<br>67.3|
|||One-stage Methods|
|ROMP [35]_†_<br>BEV [37]_†_<br>AiOS0_._5<br>AiOS0_._3|0.91<br>0.93<br>0.94<br>**0.96**|0.95<br>0.88<br>113.6<br>118.8<br>103.4<br>108.1<br>0.96<br>0.90<br>108.3<br>113.2<br>100.7<br>105.3<br>**0.98**<br>0.90<br>**61.2**<br>**68.0**<br>**57.5**<br>**63.9**<br>0.97<br>**0.95**<br>63.4<br>70.1<br>60.9<br>67.3|



Table 2. **AGORA SMPL test set** . _†_ indicates that this method is fine-tuned on the AGORA training set. AiOS0 _._ 5 and AiOS0 _._ 3, representing the use of a 0.5 score threshold and a 0.3 score threshold to filter the data, respectively. 

categorized into top-down methods [10, 13, 14, 17, 19, 20, 32, 51] and one-stage methods [35, 37], on the AGORA SMPL test set. Specifically, we downsample the SMPLX mesh estimated by AiOS to the SMPL [25] mesh using official tools [30] and then measure MVE and NMVE. We use the J-regressor to regress joints from the downsampled SMPL mesh to measure NMJE and MPJPE. 

As shown in Table 2, even though AiOS is designed for EHPS, it still outperforms ROMP [35] and BEV [37], with a notable improvement in NMVE of 43% (from 108.3 mm to 61.2 mm) and an NMJE enhancement of 40% (from 113.2 mm to 68.0 mm). It is worth noting that we do not deliberately fine-tune our model exclusively on AGORA. **Single datasets.** We compare UBody in Table 3, EHF in Table 4. Note that the other methods utilize ground-truth bounding boxes. Without any given bounding boxes, our model achieves SOTA performance on real-life datasets. 

## **4.3. Qualitative comparison with SOTA** 

We perform a qualitative comparison with current SOTA methods on AGORA and EHF. To overlay the results onto the image, we apply an affine transformation for the twostage methods that use images cropped by ground truth boxes. 

|Method|PA-PVE_↓_(_mm_)<br>All<br>Hands<br>Face|PVE_↓_(_mm_)<br>All<br>Hands<br>Face|
|---|---|---|
|PIXIE [11]<br>H4W [26]<br>OSX [21]<br>OSX [21]_†_<br>SMPLer-X [3]<br>SMPLer-X [3]_†_<br>Native AiOS<br>AiOS|61.7<br>12.2<br>4.2<br>44.8<br>8.9<br>2.8<br>42.4<br>10.8<br>2.4<br>42.2<br>8.6<br>**2.0**<br>33.2<br>10.6<br>2.8<br>**31.9**<br>10.3<br>2.8<br>35.6<br>8.6<br>2.9<br>32.5<br>**7.3**<br>2.8|168.4<br>55.6<br>45.2<br>104.1<br>45.7<br>27.0<br>92.4<br>47.7<br>24.9<br>81.9<br>41.5<br>21.2<br>61.5<br>43.3<br>23.1<br>**57.4**<br>40.2<br>21.6<br>62.7<br>41.3<br>20.8<br>58.6<br>**39.0**<br>**19.6**|



Table 3. **UBody.** _†_ indicates the model is finetuned with the UBody training set. 

|Method|PA-PVE_↓_(_mm_)<br>All<br>Hands<br>Face|PVE_↓_(_mm_)<br>All<br>Hands<br>Face|
|---|---|---|
|H4W [26]<br>OSX [21]<br>SMPLer-X [3]<br>Native AiOS<br>AiOS|50.3<br>**10.8**<br>5.8<br>48.7<br>15.9<br>6.0<br>37.8<br>15.0<br>5.1<br>38.8<br>13.8<br>4.0<br>**34.0**<br>12.8<br>**3.8**|76.8<br>**39.8**<br>26.1<br>70.8<br>53.7<br>26.4<br>65.4<br>49.4<br>17.4<br>50.2<br>49.8<br>17.3<br>**45.4**<br>44.1<br>**16.9**|



Table 4. **EHF** . As EHF is absent from our training data, it serves as a valuable tool to assess the generalization ability of our models. 

In contrast, our method can be directly overlaid on the image. Further, with accurate betas estimation, we are able to recover the depth order, as shown in the Fig. 3. We achieve comparable visual quality in both scenes, proving our model’s accuracy. 

We further perform a qualitative comparison with SOTA one-stage methods [35, 37]. As shown in Fig. 4, while ROMP and BEV can achieve decent results for body reconstruction in multi-person scenarios, they are limited by the constraints of the SMPL [25] model, preventing them from reconstructing detailed hand gestures and facial expressions. 

## **4.4. Ablation Study** 

In this subsection, we analyze the effectiveness of the proposed components in detail. All experiments are conducted 

1839 

**==> picture [414 x 94] intentionally omitted <==**

**----- Start of picture text -----**<br>
Input OSX SMPLer-X Ours Ours<br>Input Hand4Whole OSX SMPLer-X Ours<br>**----- End of picture text -----**<br>


Figure 3. Comparison of current SOTA methods [3, 21, 26] with our AiOS model. The upper part is visualization results on AGORA [28], and the lower is EHF test [7]. 

**==> picture [391 x 7] intentionally omitted <==**

**----- Start of picture text -----**<br>
Input ROMP BEV Ours<br>**----- End of picture text -----**<br>


Figure 4. Visual comparisons with SOTA one-stage HPS methods [35, 37] on the Internet data[3] . 

on the AGORA validation set. 

**Analysis of the naive AiOS and full AiOS.** Whole-body mesh recovery requires attention to both small-scale gestures, expression details, and large-scale pose details. To validate the effectiveness of our joint-guided local feature query, we compared naive AiOS and full AiOS models across the benchmarks. The table shows that even the naive setting 

> 3https://www.pexels.com/ 

achieves comparable performance with SOTA methods, indicating our one-stage pipeline, which treats EHPS as a progressive set prediction problem with various sequential detections following the DETR, is ideal for SMPL-X parameter regression. On this solid base, the full AiOS consistently achieves higher accuracy on all parts of the human, and the increment on the whole-body aspect is especially outstanding. Since the body tends to have a relatively higher area on 

1840 

**==> picture [172 x 69] intentionally omitted <==**

**----- Start of picture text -----**<br>
Body Box Center Right Knee Joint Left Hand Box Left Thumb Joint<br>— a — ae — Lal —<br>Body Box Right Hand Box Left Hand Box Face Box<br>**----- End of picture text -----**<br>


Figure 5. **Attention Visualization.** The green dots represent the location of the reference point, and the red dots are the sampling points. 

the image, adding joint queries to the body provides a large number of local features for reference, while for smaller areas like face and gestures, the difference between global and local features is not that obvious. However, adding the local joints feature overall brings more comprehensive features. 

**The Scheme of the SMPL-X supervision.** In this part, we investigate how to supervise different tokens. For our original AiOS, we don’t supervise the SMPL-X parameter in the first stage, as we want the model to focus on body localization. In the second stage, we don’t supervise hands and face for the same reason, but supervise SMPL-X body parameters as we have detailed body feature tokens. And we supervise the whole body parameter at the third stage. In the first ablation setting, we add body parameter supervision in every stage and hand and face supervision in the second stage, meaning every stage has SMPL-X supervision. In the second setting, we remove the SMPL-X body supervision in the second stage so that the model will be only supervised by SMPL-X in the last stage. As shown in Table 5, a comparison between AiOS and all stage settings shows adding SMPL-X parameters when the location is not properly refined will hinder the model’s performance. Comparing the AiOS and 3rd stage setting shows the design of gradually whole-body estimation from body to whole-body increased performance. 

**The association between the human body, hands, and face.** We focus on the self-attention relations on this part. Our stock design allows free attention among body, face, and hand location tokens, but limits joint tokens to only attend with tokens belonging to the same human. In the full attention setting, we allow tokens to any other tokens. The inter-person setting will further limit the hand and face location tokens to attend with only its subject. As shown in Table 5, the unlimited setting is the worst, as the complicated attention mechanism is not properly learned. And the limited setting is also not ideal compared to our original attention mechanism. Furthermore, we visualize the cross-attention of our model. As shown in Fig. 5, our model is able to 

|Ablation Studies|PA-PVE_↓_(_mm_)|PA-PVE_↓_(_mm_)|PA-PVE_↓_(_mm_)||PVE_↓_(_mm_)||
|---|---|---|---|---|---|---|
||All|Hands|Face|All|Hands|Face|
||Attention Format||Attention Format||||
|Full|42.5|7.2|4.2|54.8|39.0|25.8|
|Inter-human Only|41.7|7.3|4.2|52.8|38.9|24.5|
|Ours|**39.9**|**7.2**|**4.1**|**50.5**|**37.4**|**23.3**|
|SMPL-X Supervision Manners||SMPL-X Supervision Manners|||||
|All stages|42.7|7.4|4.2|55.7|39.8|25.1|
|3rd stage only|40.3|7.2|4.2|51.8|38.0|23.8|
|Ours (2,3 stage)|**39.9**|**7.2**|**4.1**|**50.5**|**37.4**|**23.3**|



Table 5. **Ablation Studies** . The upper part studies the attention format, and the bottom part studies the SMPL-X supervision manners. 

localize global features with body location tokens and local features with joint tokens. The lower part shows the attention map under occlusion, and it shows that our model will take reference from other body parts. 

## **5. Conclusion** 

In this work, we propose the first all-in-one-stage model for expressive human pose and shape estimation. We explored the incorporation of body-, face-, and hand-related tokens, as well as the aggregation of local and global features with various supervision. Moreover, we carefully designed a selfattention mechanism to establish the associations between inter- and intra-human body and body parts, which helps us to achieve its best performance. The SOTA results indicate our one-stage pipeline, which treats EHPS as a progressive set prediction problem with various sequential detections following the DETR, is a crucial factor contributing to the overall performance. This can be further proved by the performance of our naive AiOS baseline. We hope this work can contribute new insights to the EHPS research community. **Limitations.** First, our model achieves SOTA, but there is still a large room for improvement if we add more datasets for training, particularly those containing multi-person real data. Second, the versatile design can be further extended with more dimensions of human perception tasks such as tracking and 3D localization. Exploring the estimation of hands under limited resolution is also worth investigating. 

**Acknowledgement.** This project is supported by the Hong Kong Innovation and Technology Commission (InnoHK Project CIMDA). It is also supported by the Ministry of Education, Singapore, under its MOE AcRF Tier 2 (MOET2EP20221- 0012), NTU NAP, and under the RIE2020 Industry Alignment Fund – Industry Collaboration Projects (IAF-ICP) Funding Initiative, as well as cash and in-kind contribution from the industry partner(s). 

1841 

## **References** 

- [1] Michael J Black, Priyanka Patel, Joachim Tesch, and Jinlong Yang. Bedlam: A synthetic dataset of bodies exhibiting detailed lifelike animated motion. In _IEEE Conf. Comput. Vis. Pattern Recog._ , pages 8726–8737, 2023. 2, 5, 6 

- [2] Zhongang Cai, Daxuan Ren, Ailing Zeng, Zhengyu Lin, Tao Yu, Wenjia Wang, Xiangyu Fan, Yang Gao, Yifan Yu, Liang Pan, et al. Humman: Multi-modal 4d human dataset for versatile sensing and modeling. In _Eur. Conf. Comput. Vis._ , pages 557–577. Springer, 2022. 2 

- [3] Zhongang Cai, Wanqi Yin, Ailing Zeng, Chen Wei, Qingping Sun, Yanjun Wang, Hui En Pang, Haiyi Mei, Mingyuan Zhang, Lei Zhang, et al. Smpler-x: Scaling up expressive human pose and shape estimation. _arXiv preprint arXiv:2309.17448_ , 2023. 2, 5, 6, 7 

- [4] Zhongang Cai, Mingyuan Zhang, Jiawei Ren, Chen Wei, Daxuan Ren, Zhengyu Lin, Haiyu Zhao, Lei Yang, and Ziwei Liu. Playing for 3d human recovery. _arXiv preprint arXiv:2110.07588_ , 2021. 2 

- [5] Nicolas Carion, Francisco Massa, Gabriel Synnaeve, Nicolas Usunier, Alexander Kirillov, and Sergey Zagoruyko. End-toend object detection with transformers. In _Eur. Conf. Comput. Vis._ , pages 213–229. Springer, 2020. 2, 3 

- [6] Junhyeong Cho, Kim Youwang, and Tae-Hyun Oh. Crossattention of disentangled modalities for 3d human mesh recovery with transformers. In _Eur. Conf. Comput. Vis._ , pages 342–359. Springer, 2022. 2 

- [7] Vasileios Choutas, Georgios Pavlakos, Timo Bolkart, Dimitrios Tzionas, and Michael J Black. Monocular expressive body regression through body-driven attention. In _Eur. Conf. Comput. Vis._ , pages 20–40. Springer, 2020. 2, 7 

- [8] Zhiyang Dou, Qingxuan Wu, Cheng Lin, Zeyu Cao, Qiangqiang Wu, Weilin Wan, Taku Komura, and Wenping Wang. Tore: Token reduction for efficient human mesh recovery with transformer. _arXiv preprint arXiv:2211.10705_ , 2022. 2 

- [9] Zicong Fan, Omid Taheri, Dimitrios Tzionas, Muhammed Kocabas, Manuel Kaufmann, Michael J Black, and Otmar Hilliges. Arctic: A dataset for dexterous bimanual handobject manipulation. In _IEEE Conf. Comput. Vis. Pattern Recog._ , pages 12943–12954, 2023. 5 

- [10] Qi Fang, Kang Chen, Yinghui Fan, Qing Shuai, Jiefeng Li, and Weidong Zhang. Learning analytical posterior probability for human mesh recovery. In _IEEE Conf. Comput. Vis. Pattern Recog._ , 2023. 6 

- [11] Yao Feng, Vasileios Choutas, Timo Bolkart, Dimitrios Tzionas, and Michael Black. Collaborative regression of expressive bodies using moderation. In _International Conference on 3D Vision (3DV)_ , pages 792–804, Dec. 2021. 2, 6 

- [12] Kaiming He, Xiangyu Zhang, Shaoqing Ren, and Jian Sun. Deep residual learning for image recognition. In _IEEE Conf. Comput. Vis. Pattern Recog._ , pages 770–778, 2016. 3 

- [13] Angjoo Kanazawa, Michael J Black, David W Jacobs, and Jitendra Malik. End-to-end recovery of human shape and pose. In _IEEE Conf. Comput. Vis. Pattern Recog._ , pages 7122–7131, 2018. 2, 6 

- [14] Muhammed Kocabas, Chun-Hao P Huang, Otmar Hilliges, 

   - and Michael J Black. Pare: Part attention regressor for 3d human body estimation. In _Int. Conf. Comput. Vis._ , pages 11127–11137, 2021. 2, 6 

- [15] Nikos Kolotouros, Georgios Pavlakos, Michael J Black, and Kostas Daniilidis. Learning to reconstruct 3d human pose and shape via model-fitting in the loop. In _Int. Conf. Comput. Vis._ , pages 2252–2261, 2019. 2 

- [16] Nikos Kolotouros, Georgios Pavlakos, and Kostas Daniilidis. Convolutional mesh regression for single-image human shape reconstruction. In _IEEE Conf. Comput. Vis. Pattern Recog._ , pages 4501–4510, 2019. 2 

- [17] Jiefeng Li, Siyuan Bian, Qi Liu, Jiasheng Tang, Fan Wang, and Cewu Lu. NIKI: Neural inverse kinematics with invertible neural networks for 3d human pose and shape estimation. In _IEEE Conf. Comput. Vis. Pattern Recog._ , June 2023. 6 

- [18] Jiefeng Li, Siyuan Bian, Chao Xu, Zhicun Chen, Lixin Yang, and Cewu Lu. Hybrik-x: Hybrid analytical-neural inverse kinematics for whole-body mesh recovery. _arXiv preprint arXiv:2304.05690_ , 2023. 2, 6 

- [19] Jiefeng Li, Chao Xu, Zhicun Chen, Siyuan Bian, Lixin Yang, and Cewu Lu. Hybrik: A hybrid analytical-neural inverse kinematics solution for 3d human pose and shape estimation. In _IEEE Conf. Comput. Vis. Pattern Recog._ , pages 3383–3393, 2021. 2, 6 

- [20] Zhihao Li, Jianzhuang Liu, Zhensong Zhang, Songcen Xu, and Youliang Yan. Cliff: Carrying location information in full frames into human pose and shape estimation. In _Eur. Conf. Comput. Vis._ , pages 590–606. Springer, 2022. 2, 3, 6 

- [21] Jing Lin, Ailing Zeng, Haoqian Wang, Lei Zhang, and Yu Li. One-stage 3d whole-body mesh recovery with component aware transformer. In _IEEE Conf. Comput. Vis. Pattern Recog._ , pages 21159–21168, 2023. 2, 5, 6, 7 

- [22] Kevin Lin, Lijuan Wang, and Zicheng Liu. Mesh graphormer. In _Int. Conf. Comput. Vis._ , pages 12939–12948, 2021. 2 

- [23] Tsung-Yi Lin, Michael Maire, Serge Belongie, James Hays, Pietro Perona, Deva Ramanan, Piotr Dollár, and C Lawrence Zitnick. Microsoft coco: Common objects in context. In _Eur. Conf. Comput. Vis._ , pages 740–755. Springer, 2014. 5 

- [24] Shilong Liu, Feng Li, Hao Zhang, Xiao Yang, Xianbiao Qi, Hang Su, Jun Zhu, and Lei Zhang. DAB-DETR: Dynamic anchor boxes are better queries for DETR. In _Int. Conf. Learn. Represent._ , 2022. 3 

- [25] Matthew Loper, Naureen Mahmood, Javier Romero, Gerard Pons-Moll, and Michael J Black. Smpl: A skinned multiperson linear model. _ACM Trans. Graph._ , 34(6):1–16, 2015. 6 

- [26] Gyeongsik Moon, Hongsuk Choi, and Kyoung Mu Lee. Accurate 3d hand pose estimation for whole-body 3d human mesh estimation. In _IEEE Conf. Comput. Vis. Pattern Recog. Worksh._ , 2022. 2, 5, 6, 7 

- [27] Hui En Pang, Zhongang Cai, Lei Yang, Qingyi Tao, Zhonghua Wu, Tianwei Zhang, and Ziwei Liu. Towards robust and expressive whole-body human pose and shape estimation. In _Adv. Neural Inform. Process. Syst._ , 2023. 2 

- [28] Priyanka Patel, Chun-Hao P Huang, Joachim Tesch, David T Hoffmann, Shashank Tripathi, and Michael J Black. AGORA: Avatars in geography optimized for regression analysis. In _IEEE Conf. Comput. Vis. Pattern Recog._ , pages 13468–13478, 2021. 2, 5, 7 

1842 

- [29] Georgios Pavlakos, Vasileios Choutas, Timo Bolkart, Dimitrios Tzionas, Michael J. Black, Vasileios Choutas, Georgios Pavlakos, Timo Bolkart, Dimitrios Tzionas, and Michael J. Black. Monocular expressive body regression through bodydriven attention. _Eur. Conf. Comput. Vis._ , 2020. 2 

- [30] Georgios Pavlakos, Vasileios Choutas, Nima Ghorbani, Timo Bolkart, Ahmed A. Osman, Dimitrios Tzionas, and Michael J. Black. Expressive body capture: 3d hands, face, and body from a single image. In _IEEE Conf. Comput. Vis. Pattern Recog._ , 2019. 1, 2, 3, 5, 6 

- [31] Yu Rong, Takaaki Shiratori, and Hanbyul Joo. Frankmocap: A monocular 3d whole-body pose estimation system via regression and integration. In _Int. Conf. Comput. Vis. Worksh._ , 2021. 2 

- [32] Karthik Shetty, Annette Birkhold, Srikrishna Jaganathan, Norbert Strobel, Markus Kowarschik, Andreas Maier, and Bernhard Egger. Pliks: A pseudo-linear inverse kinematic solver for 3d human body estimation. In _IEEE Conf. Comput. Vis. Pattern Recog._ , pages 574–584, 2023. 6 

- [33] Dahu Shi, Xing Wei, Liangqi Li, Ye Ren, and Wenming Tan. End-to-end multi-person pose estimation with transformers. In _IEEE Conf. Comput. Vis. Pattern Recog._ , pages 11059– 11068, 2022. 3 

- [34] Qingping Sun, Yi Xiao, Jie Zhang, Shizhe Zhou, Chi-Sing Leung, and Xin Su. A local correspondence-aware hybrid cnn-gcn model for single-image human body reconstruction. _IEEE Transactions on Multimedia_ , 25:4679–4690, 2023. 2 

- [35] Yu Sun, Qian Bao, Wu Liu, Yili Fu, Michael J Black, and Tao Mei. Monocular, one-stage, regression of multiple 3d people. In _Int. Conf. Comput. Vis._ , pages 11179–11188, 2021. 2, 3, 4, 6, 7 

- [36] Yu Sun, Qian Bao, Wu Liu, Tao Mei, and Michael J Black. Trace: 5d temporal regression of avatars with dynamic cameras in 3d environments. In _IEEE Conf. Comput. Vis. Pattern Recog._ , pages 8856–8866, 2023. 3 

- [37] Yu Sun, Wu Liu, Qian Bao, Yili Fu, Tao Mei, and Michael J Black. Putting people in their place: Monocular regression of 3d people in depth. In _IEEE Conf. Comput. Vis. Pattern Recog._ , pages 13243–13252, 2022. 2, 3, 4, 6, 7 

- [38] Ashish Vaswani, Noam Shazeer, Niki Parmar, Jakob Uszkoreit, Llion Jones, Aidan N Gomez, Łukasz Kaiser, and Illia Polosukhin. Attention is all you need. _Adv. Neural Inform. Process. Syst._ , 30, 2017. 3 

- [39] Wenjia Wang, Yongtao Ge, Haiyi Mei, Zhongang Cai, Qingping Sun, Yanjun Wang, Chunhua Shen, Lei Yang, and Taku Komura. Zolly: Zoom focal length correctly for perspective-distorted human mesh reconstruction. _arXiv preprint arXiv:2303.13796_ , 2023. 2 

- [40] Yanjun Wang, Qingping Sun, Wenjia Wang, Jun Ling, Zhongang Cai, Rong Xie, and Li Song. Learning dense uv completion for human mesh recovery. _arXiv preprint arXiv:2307.11074_ , 2023. 2 

   - [43] Zhitao Yang, Zhongang Cai, Haiyi Mei, Shuai Liu, Zhaoxi Chen, Weiye Xiao, Yukun Wei, Zhongfei Qing, Chen Wei, Bo Dai, et al. Synbody: Synthetic dataset with layered human models for 3d human perception and modeling. _arXiv preprint arXiv:2303.17368_ , 2023. 2 

   - [44] Ailing Zeng, Xuan Ju, Lei Yang, Ruiyuan Gao, Xizhou Zhu, Bo Dai, and Qiang Xu. Deciwatch: A simple baseline for 10 _×_ efficient 2d and 3d pose estimation. In _Eur. Conf. Comput. Vis._ , pages 607–624. Springer, 2022. 2 

   - [45] Ailing Zeng, Lei Yang, Xuan Ju, Jiefeng Li, Jianyi Wang, and Qiang Xu. Smoothnet: A plug-and-play network for refining human poses in videos. In _Eur. Conf. Comput. Vis._ , pages 625–642. Springer, 2022. 2 

   - [46] Fangao Zeng, Bin Dong, Yuang Zhang, Tiancai Wang, Xiangyu Zhang, and Yichen Wei. Motr: End-to-end multipleobject tracking with transformer. In _Eur. Conf. Comput. Vis._ , 2022. 2 

   - [47] Wang Zeng, Wanli Ouyang, Ping Luo, Wentao Liu, and Xiaogang Wang. 3d human mesh regression with dense correspondence. In _IEEE Conf. Comput. Vis. Pattern Recog._ , pages 7054–7063, 2020. 2 

   - [48] Aixi Zhang, Yue Liao, Si Liu, Miao Lu, Yongliang Wang, Chen Gao, and Xiaobo Li. Mining the benefits of two-stage and one-stage hoi detection. _Adv. Neural Inform. Process. Syst._ , 34:17209–17220, 2021. 2 

   - [49] Hao Zhang, Feng Li, Shilong Liu, Lei Zhang, Hang Su, Jun Zhu, Lionel M Ni, and Heung-Yeung Shum. Dino: Detr with improved denoising anchor boxes for end-to-end object detection. _arXiv preprint arXiv:2203.03605_ , 2022. 3 

   - [50] Hongwen Zhang, Yating Tian, Yuxiang Zhang, Mengcheng Li, Liang An, Zhenan Sun, and Yebin Liu. Pymaf-x: Towards well-aligned full-body model regression from monocular images. _IEEE Trans. Pattern Anal. Mach. Intell._ , 2023. 6 

   - [51] Hongwen Zhang, Yating Tian, Xinchi Zhou, Wanli Ouyang, Yebin Liu, Limin Wang, and Zhenan Sun. Pymaf: 3d human pose and shape regression with pyramidal mesh alignment feedback loop. In _Int. Conf. Comput. Vis._ , 2021. 2, 6 

   - [52] Siwei Zhang, Qianli Ma, Yan Zhang, Zhiyin Qian, Taein Kwon, Marc Pollefeys, Federica Bogo, and Siyu Tang. Egobody: Human body shape and motion of interacting people from head-mounted devices. In _Eur. Conf. Comput. Vis._ , pages 180–200. Springer, 2022. 5 

   - [53] Xizhou Zhu, Weijie Su, Lewei Lu, Bin Li, Xiaogang Wang, and Jifeng Dai. Deformable detr: Deformable transformers for end-to-end object detection. _arXiv preprint arXiv:2010.04159_ , 2020. 3 

   - [54] Cheng Zou, Bohan Wang, Yue Hu, Junqi Liu, Qian Wu, Yu Zhao, Boxun Li, Chenguang Zhang, Chi Zhang, Yichen Wei, et al. End-to-end human object interaction detection with hoi transformer. In _IEEE Conf. Comput. Vis. Pattern Recog._ , pages 11825–11834, 2021. 2 

- [41] Jie Yang, Ailing Zeng, Feng Li, Shilong Liu, Ruimao Zhang, and Lei Zhang. Neural interactive keypoint detection. In _Int. Conf. Comput. Vis._ , pages 15122–15132, 2023. 2 

- [42] Jie Yang, Ailing Zeng, Shilong Liu, Feng Li, Ruimao Zhang, and Lei Zhang. Explicit box detection unifies end-to-end multi-person pose estimation. _arXiv preprint arXiv:2302.01593_ , 2023. 2, 3 

1843 

