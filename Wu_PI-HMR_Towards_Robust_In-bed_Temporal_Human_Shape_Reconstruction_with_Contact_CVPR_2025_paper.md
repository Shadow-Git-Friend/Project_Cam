This CVPR paper is the Open Access version, provided by the Computer Vision Foundation. Except for this watermark, it is identical to the accepted version; the final published version of the proceedings is available on IEEE Xplore. 

## **PI-HMR: Towards Robust In-bed Temporal Human Shape Reconstruction with Contact Pressure Sensing** 

Ziyu Wu[*] , Yufan Xiong[*] , Mengting Niu, Fangting Xie, Quan Wan, Qijun Ying, Boyan Liu, Xiaohui Cai[†] University of Science and Technology of China 

**==> picture [496 x 140] intentionally omitted <==**

**----- Start of picture text -----**<br>
(a) SMPLify-IB (b) PI-HMR<br>Optimization<br>ii 0] t = 1 SSBRQHN0OR t = 11<br>ia 08 sg0gg00000<br>Figure 1. We present a general framework for in-bed HPS tasks, containing a monocular optimization strategy to generate high-quality<br>SMPL annotations in in-bed scenarios, SMPLify-IB; and a HPS network to predict in-bed motions from pressure sequence, PI-HMR.<br>**----- End of picture text -----**<br>


## **Abstract** 

## **1. Introduction** 

_Long-term in-bed monitoring benefits automatic and realtime health management within healthcare, and the advancement of human shape reconstruction technologies further enhances the representation and visualization of users’ activity patterns. However, existing technologies are primarily based on visual cues, facing serious challenges in non-light-of-sight and privacy-sensitive in-bed scenes. Pressure-sensing bedsheets offer a promising solution for real-time motion reconstruction. Yet, limited exploration in model designs and data have hindered its further development. To tackle these issues, we propose a general framework that bridges gaps in data annotation and model design. Firstly, we introduce SMPLify-IB, an optimization method that overcomes the depth ambiguity issue in topview scenarios through gravity constraints, enabling generating high-quality 3D human shape annotations for inbed datasets. Then we present PI-HMR, a temporal-based human shape estimator to regress meshes from pressure sequences. By integrating multi-scale feature fusion with high-pressure distribution and spatial position priors, PIHMR outperforms SOTA methods with 17.01mm Mean-PerJoint-Error decrease. This work provides a whole toolchain to support the development of in-bed monitoring with pressure contact sensing._ 

> *These authors contributed equally to this work. 

> †Corresponding authors. 

Long-term and automatic in-bed monitoring draws increasing attention in recent years for the growing need in heathcare, such as sleep studies [5], bedsore prevention [57], and detection of bed-exit and fall events [19]. The advancement of parameterized human representation ( _e.g_ . SMPL [35]) and human pose and shape estimation (HPS) technologies further furnish technical underpinning for the reconstruction and visualization of patient motions, facilitating caregivers to comprehend patients’ behavioral patterns in time. However, vision-based techniques, trained on in-lab or in-wild public datasets, fail in in-bed scenarios for more challenges are raised like poor illumination, occlusion by blankets, domain gaps with existing datasets ( _e.g_ . 3DPW [49]), and privacy issues in both at-home or ICUs. 

Our intuition lies in that tactile serves as a crucial medium for human perception of the surroundings. Especially for in-bed scenarios, lying postures prompt full engagement between humans and environment; simultaneously, this tactile perception also encompasses valuable information about their physiques. Reconstructing human motions from this tactile feedback might provide a privacypreserving solution to automatic in-bed management for patients and elders. Thus, many efforts have been devoted to capturing the contact pressure with a pressure-sensing bedsheet, which integrates a pressure-sensitive sensor array and collects matrix-formatted pressure distribution (named pressure images), and exploring potentials of full-body human reconstruction from these tactile sensors [8, 9, 46]. However, current methods are often constrained by model 

27739 

design, dataset diversity and label quality. The limitations can be categorized into three points: 

(1) **Lack of explorations on the pressure nature** . Despite both RGB and pressure images sharing similar structures, the meaning of each pixel differs significantly. For visual images, both foreground and background pixels are non-trivial, conveying texture and semantics. Nonetheless, with single-channel pressure data, regions lacking applied pressure are denoted as zeros, resulting in a dearth of semantic cues regarding the background. Furthermore, the relationship between pressure contours and human shapes introduces information ambiguity [46, 55] when some crucial joints do not directly interact with sensors. Previous research [9, 46] attempted to estimate pressure based on the penetration depth of the human model and contact surfaces, thereby explicitly introducing pressure supervision. However, due to limitations in SMPL vertices granularity, sensor resolution, and tissue deformation, SMPL struggles to describe the contact mode with outsides, thus potentially impairing model performance. Consequently, hasty adoption of visual pipelines, without tailored design for pressure characteristics, might restrict model performance. 

(2) **Limited data diversity** . Data diversity implicates models’ generalization to unseen situations. For visionbased HPS tasks, the flourishing of HPS community is contributed by large-scale general ( _e.g_ . ImageNet [11]) or task-specific ( _e.g_ . AMASS [37]) datasets and mass of unlabeled data from Internet. However, as a human-centric and sensor-based task, in addition to the SLP [34] dataset that contains data from 102 individuals, most in-bed pressure datasets include fewer than 20 participants. Furthermore, the disparities of the sensor scale and performance across different studies, making it challenging to integrate these datasets, thus leading to poor performance to out-ofdistribution users or motions. Therefore, how to learn priors across datasets and modalities is of paramount significance. 

(3) **Limited 3D label quality** . One main factor limiting the data diversity is the challenge of acquiring accurate 3D labels, especially for an in-bed setting. Currently, only SLP [34] and TIP [52] datasets offer both SMPL pseudoground truth (p-GTs) and RGB images, with annotations in TIP being seriously doubted by depth ambiguity and penetrations due to monocular SMPLify-based optimization (in Fig. 2). Limited label quality might lead the model to misinterpret pressure cues, thus calling for a low-cost and accurate label annotation approach for in-bed scenes. 

To tackle aforesaid disparities, in this work, we present a general framework bridging from annotations, model design and evaluation for pressure-based in-bed HPS tasks. Concretely, we firstly present PI-HMR, a pressure-based inbed human shape estimation network to predict human motions from pressure sequences, as a preliminary exploration to utilize pressure characteristics. Our core philosophy falls 

that both joint positions and contours of high-pressure areas are essential to sense pressure distribution and its variation patterns from the redundant zero-value backgrounds. Thus, we achieve this by explicitly introducing these semantic cues, compelling the model to focus on core regions by feature sampling. Furthermore, considering that the sensing mattress is often fixed in the environment, we leverage these positional priors and feed them into the model to learn the spatial relationship between humans and sensors. Experiments show that PI-HMR brings 17.01mm MPJPE decrease compared to PI-Mesh [52] and outperforms visionbased temporal SOTA architecture TCMR [7] (re-trained on pressure images) with 4.91mm MPJPE improvement. 

Moreover, to further expand prior distribution within limited pressure datasets, we realize (1) a Knowledge Distillation (KD) [18] framework to pre-train PI-HMR’s encoder with RGB-based SOTA method CLIFF [30], to facilitate cross-modal body and motion priors transfer; and (2) a pretrained VQ-VAE [47] network as in-bed motion priors in a unsupervised Test-Time Optimization to alleviate information ambiguity. Experiments show that both modules bring 2.33mm and 1.7mm MPJPE decrease, respectively. 

Finally, for a low-cost but efficient label annotation method tailored for in-bed scenes, we present a monocular optimization approach, SMPLify-IB. It incorporates a gravity-constraint term to address depth ambiguity issues in in-bed scenes, and integrates a potential-based penalty term with a lightweight self-contact detection module to alleviate limb penetrations. We re-generated 3D p-GTs in the TIP [52] dataset and results show that SMPLify-IB not only provides higher-quality annotations but also mitigates implausible limb lifts. This suggests the feasibility of addressing depth ambiguity issues with physical constraints in specific scenarios. Besides, results prove that our detection module is 53.9 times faster than SMPLify-XMC [38] while achieving 98.32% detection accuracy. 

We highlight our key contributions: (1) a general framework for pressure-based in-bed human shape estimation task, spanning from label generation to algorithm design. (2) PI-HMR, a temporal network to directly predict 3D meshes from in-bed pressure image sequences and outperforms both SOTA pressure-based and vision-field architectures. (3) SMPLify-IB, a gravity-based optimization technique to generate reliable SMPL p-GTs for monocular inbed scenes. Based on SMPLify-IB, we re-generate 3D annotations for a public dataset, TIP, providing higher-quality SMPL p-GTs and mitigating implausible limb lifts due to depth ambiguity. (4) We explore the feasibility of prior expansion with knowledge distillation and TTO strategy. 

## **2. Related Work** 

**Regression for HPS.** Recent years have witnessed tremendous advances in vision-based human shape recon- 

27740 

**==> picture [218 x 7] intentionally omitted <==**

**----- Start of picture text -----**<br>
RGB & 2D keypoints p-GTs from TIP p-GTs from SMPLify-IB<br>**----- End of picture text -----**<br>


involving pressure estimation to reconstruct in-bed shapes from a single pressure image [9]. Wu et al. [52] collected a three-modality in-bed dataset TIP, and employed a VIBEbased network to predict in-bed motions from pressure sequences. Yin et al. [55] proposed a pyramid scheme to infer in-bed shapes from aligned depth, LWIR, RGB, and pressure images, and Tandon et al. [46] improves accuracy on SLP [34] with depth and pressure modalities by integrating a pressure prediction module as auxiliary supervision. 

## **3. Dataset and Label Enhancement** 

## **3.1. Data Overview** 

Figure 2. A glimpse of TIP dataset, with p-GTs from TIP and our SMPLify-IB. we highlight its drawbacks with red ellipses and our refinements in yellow ones. 

struction approaches from images [12, 14, 23, 27–30, 42– 44, 50, 59] based on the parametric human body model ( _i.e_ ., SMPL [35]). Meanwhile, several works take video clips as input to exploit the temporal cues [7, 24, 26, 41, 51, 56], utilizing the temporal context to improve the smoothness. 

We mainly focus on HPS from contact pressure sensing. Unlike visual information, the representation pattern of contact pressure data is influenced by its perceptual medium, thus necessitating a corresponding alteration in algorithm design. Typical sensing devices, combined with HPS algorithms, ( _e.g_ ., carpets [6, 36], clothes [58, 61], bedsheets or mattress [9, 34, 46, 52], and shoes [48, 60]), are applied as a major modality or supplements to help generate robust body predictions in pre-defined scenes or tasks. Nevertheless, the process strategy of pressure data leans on vision pipelines, lacking a thorough contemplation of its inherent nature. 

**Optimization for HPS.** Optimization-based methods typically fit the SMPL parameters to image cues [3, 40] ( _e.g_ . detected 2D joints [4, 53]), combined with data and prior terms. Follow-up studies further introduced supplement supervisions, including, but not limited to temporal consistency [2], environment [25], human-human/scene contact [17, 20, 39], self-contact [38] and large language models (LLMs) [45] to regularize motions in specific context. Besides, in recent years, efforts have emerged to integrate both optimization and regression methods as a cheap but effective annotation technique to produce pseudo-labels for visual datasets [20, 52, 60], especially for monocular data from online images and videos [22, 31, 38, 54]. 

**In-bed human pose and shape estimation.** Compared with other human-related tasks, in-bed HPS faces more serious challenges from data quality and privacy issues. Thus, efforts are devoted to pursuing environmental sensors for in such a non-light-of-sight (NLOS) scenes, such as infrared camera [32, 33], depth camera [1, 9, 16], pressure-sensing mattresses [8–10, 52]. Specifically for pressure-based approaches, Clever et al. [9] conducted pioneering studies by 

We select TIP [52] as our evaluation dataset because, to our knowledge, it is the sole dataset containing both temporal in-bed pressure images and SMPL annotations. TIP is an in-bed posture dataset that contains over 152K synchronously-collected three-modal images (RGB, depth, and pressure) from 9 subjects, with matched 2D keypoint and 3D SMPL annotations. We present a glimpse visualization in Fig. 2. The SMPL annotations are generated by a SMPLify-like approach. However, we notice severe depth ambiguity ( _e.g_ ., mistaken limb lifts) and self-penetration in their p-GTs (marked in Fig. 2), which are common issues for monocular optimization. Considering that reliable labels are crucial for the robustness of algorithms, we presented a general optimization approach that utilizes physical constraints to generate accurate SMPL p-GTs for in-bed scenes, named SMPLify-IB, and re-generated annotations for the whole dataset. Compared with raw annotations, we have significantly enhanced the rationality of the labels (shown in Fig. 2). More results will be presented in Sec. 5.3. 

## **3.2. SMPLify-IB: Generate reliable p-GTs for TIP** 

SMPLify-IB contains two core alterations compared with traditional approaches: a gravity-based constraints to penalize implausible limb lift due to depth ambiguity, and a lightweight penetration detection algorithm with a potential-based loss term to penalize self-penetration. We briefly summarize our efforts as follows, and more details are given in the Sup. Mat.. 

## **3.2.1. Gravity Constraint** 

To tackle the implausible limb lifts, our rationale lies in the observations that when a person lies in bed, it should stay relaxed. Conversely, when limbs are intentionally lifted, a torque is generated at the shoulders or hips, thus resulting in discomfort. Such a conflict inspires us that when a person is motionless, all limbs should receive support to avoid an ”uncomfortable” posture. Based on such an intuition, we propose a zero-velocity detection algorithm to detect implausible limb suspensions caused by depth ambiguity and exert gravity constraints to push them into contact with the bed plane or other body parts for support. Specif- 

27741 

**==> picture [229 x 77] intentionally omitted <==**

**----- Start of picture text -----**<br>
S vj ' vj '<br>vi ' S<br>vi '<br>C<br>C<br>vi vj vi vj<br>e e<br>(a) 2-D demos (b) 3-D demos (c) Segments<br>**----- End of picture text -----**<br>


Figure 3. (a) and (b): demos of our detection algorithm. _S_ is the segment, _C_ is its segment center. _vi_ are vertices that need to be checked for penetration with _S_ , and _vj_ are the vertices from _S_ that are closest to _vi_ , respectively. When _[−−→] vivj ·[−−→] viC <_ 0, _vi_ is in penetration, and vice versa. (c) is our segment. 

ically, we use velocities of 2D keypoint ground-truths to calibrate limb status. For those velocities exceeding a predefined threshold, we consider them to be in normal movement states; for limbs raised but nearly static, we annotate them as miscalculations from depth ambiguity and punish their distance to the bed plane. The loss term is as follows: 

**==> picture [201 x 36] intentionally omitted <==**

where _GJ_ is the set of gravity-constrained limb joints including hands, elbows, knees, and ankles, _z_ ( _i_ ) _j_ is the signed distance of joint _j_ in timestamp _i_ to the bed plane, _v_ ( _i_ ) _j_ is its velocity, _threv_ is the velocity threshold, I is the indicator function, and _ωj_ is the hyperparameter. 

## **3.2.2. Potential-based self-penetration Constraint** 

In order to reduce complexity, we only penalize the distance between lifted limbs and the bed plane in gravity loss _Lg_ , which might further exacerbate self-penetration. Thus, the other main goal of SMPLify-IB is to punish severe self-intersection while encouraging plausible selfcontact. Given that the _Self-Contact_ approach in SMPLifyXMC [38] is slow for large-dataset annotation , we propose a lightweight self-contact supervision that includes two main parts, lightweight self-penetration detection and potential-based self-penetration penalty modules. 

**Lightweight Detection.** In SMPLify [3], authors used capsules to approximate human parts and calculate crosspart penetration. Although it’s a coarse-grained limb representation, we notice that in such a capsule, the angle formed by the capsule center, penetrating vertex, and its closest vertex on the capsule-wall is likely to be obtuse. Following the observation, instead of calculating all solid angles between 6890 SMPL vertices and 13776 triangles in _Winding Numbers_ [21] applied by SMPLify-XMC [38], we make an approximation that the SMPL vertices could be viewed as an aggregation of multiple convex, uniform, and encapsulated segments (shown in Fig. 3(c)), thus facilitating us to judge penetrations by spatial relations between vertices and segment centers. Specifically, assuming that a posed SMPL 

model could be represented by _K_ non-intersecting and convex vertex sets _{S_ 1 _, ..., SK}_ and their segment center set _{c_ 1 _, ..., cK}_ . For any vertex _vi_ from segment _Si_ , to determine whether it intersects with _Sj_ , we firstly calculate its nearest vertex in _Sj_ (noted as _vj_ ), and then judge whether intersection occurs for vertex _vi_ by the sign of dot product _−−→ vivj ·[−−→] vicj_ ( _v[−−→] ivj ·[−−→] vicj <_ 0 means _vi_ is inside the segment _Sj_ , and vice versa). We provide intuitively demos in Fig. 3. 

To construct approximately-convex segments, we predefine 24 segment centers (including 16 SMPL joints and 8 virtual joints in joint-sparse limbs like arms and legs to ensure uniformity), and employ a clustering algorithm to determine the assignment of SMPL vertices to segments. Finally, 24 segments are generated and visualized in Fig. 3(c). 

**Potential-based constraints.** Beside commonly-used point-wise contact term (noted as _Lp_ ~~_c_~~ _on_[)][and][penetration] penalty (noted as _Lp_ ~~_i_~~ _sect_[) with Signal Distance Field (SDF)] as specified in SMPLify-XMC, we notice that SMPL vertices are spatially influenced by their closest joints. Thus, we could directly penalize the distance between centers of two intersecting segments, to push these segments moving away. For two intersecting segments _Si_ and _Sj_ , and their centers _ci_ and _cj_ , we denote the penalty as: 

**==> picture [202 x 10] intentionally omitted <==**

where D is the detection algorithm and _|_ D( _Si, Sj_ ) _|_ means the number of intersecting vertices. Similarly, we use the same version to represent the self-contact term to encourage those close but non-intersected segments to contact: 

**==> picture [202 x 10] intentionally omitted <==**

where C is the contact detection algorithm ( _i.e_ ., SDF of two vertices between 0 - 0.02m). Both terms are constrained by set scales and center distances, acting like repulsive forces between clusters, thus named potential constraints. 

Finally, we could get the whole penetration term _Lsc_ . 

**==> picture [197 x 10] intentionally omitted <==**

## **3.2.3. SMPLify-IB** 

Finally, we present SMPLify-IB, a two-stage optimization method for SMPL p-GTs from monocular images. In the first stage, we use the CLIFF predictions as initialization and jointly optimize the shape parameter _β_ , translation parameter _t_ , and pose parameter _θ_ . After that, we use the mean shape parameters of all frames from the same subject as its shape ground truths. In the second stage, we freeze _β_ and only optimize _t_ and _θ_ . Both stages share the same objective functions Eq. (5), exhibited as follows: 

**==> picture [209 x 24] intentionally omitted <==**

Besides the gravity loss _Lg_ and self-penetration term _Lsc_ , _LJ_ and _Lp_ denotes the re-projection term and prior term, as 

27742 

**==> picture [492 x 181] intentionally omitted <==**

**----- Start of picture text -----**<br>
Pressure Sequence Static Features Fused Features Temporal Features Target<br>T = 1 x1 g1 𝑧𝑧1<br>Transformer<br>block<br>𝑁𝑁 Multi-Scale SMPL<br>T = 2 Encoder x𝑁𝑁/2 FeatureFusion  g𝑁𝑁/2 z𝑁𝑁/2 M ̅𝑍𝑍 Regressor<br>Module Transformer<br>block<br>T = 𝑁𝑁 xT gT 𝑧𝑧T<br>po o m che~ M [: Mean]<br>Figure 4. An overview of PI-HMR.  PI-HMR outputs the midframe’s SMPL predictions of the whole sequence.<br>specified in [3]; Lsm is the smooth term and Lcons is the tions, always accompanied by inherent information ambi-<br>consistency loss that penalizes the differences between the guity, serve to assist the model in learning the local pres-<br>overlapped part of adjacent batches; and  Lbc is the human- sure distribution pattern between small and large pressure<br>bed penetration loss, which is the same as [52]. zones. Following the insight, we present the Multi-scale<br>… … … … …<br>… … … … …<br>**----- End of picture text -----**<br>


tions, always accompanied by inherent information ambiguity, serve to assist the model in learning the local pressure distribution pattern between small and large pressure zones. Following the insight, we present the Multi-scale Feature Fusion module (MFF), shown in Fig. 5. MFF extracts multi-scale features from the static feature _xi_ with the supervision of high-pressure masks and human joints, and generates the fusion feature _gi_ for the next-stage temporal encoder. Before delving into MFF, we first introduce our positional encoding and high-pressure sampling strategy. 

## **4. Method** 

## **4.1. PI-HMR** 

Our motivation is to utilize pressure data nature. So our efforts fall into three stages: alleviating the dataset bottleneck and learning cross-dataset human and motion priors in the pre-training stage; pressure-based PI-HMR’s design; and learning user’s habits to overcome information ambiguity in the TTO. Thus, the data flow includes: (1) pre-train: KD-based pre-training with the training set; (2) train: train the PI-HMR and VQ-VAE with the training set; (3) test: test with PI-HMR on the test set and improve the estimates with the TTO strategy. Fig. 4 shows the framework of PI-HMR. The details of each module will be elaborated as follows: 

**Spatial Position Embedding.** We introduce a novel position embedding approach to fuse spatial priors into model learning. Compared with visual pixels, we could acquire the position of each sensing unit and their spatial relationships, given that the sensors remain fixed during data collection. Specifically, for a sensing unit located in pixel ( _i, j_ ) of a pressure image, we could get its position representation [ _i, j, i · dh, j · dw_ ], with _dh_ , _dw_ being the sensor intervals along x-axis and y-axis ( _dh_ = 0 _._ 0311 _m_ and _dw_ = 0 _._ 0195 _m_ in TIP). The first two values mean its position within image, while the latter ones denote the position in the world coordinate system (with its origin at the top-left pixel position of the pressure image). The representation is then transformed into spatial tokens _P ∈_ R[256] using a linear layer. During the training, we could generate the spatial position map for the whole pressure image, noted as _Pi ∈_ R[256] _[×][H][×][W]_ . 

## **4.1.1. Overall Pipeline of PI-HMR** 

Given an input pressure image sequence _V_ = _{Ii ∈_ R _[H][×][W] }[T] t_ =1[with] _[T]_[frames,][PI-HMR][outputs][the][SMPL] predictions of the mid-frame by a three-stage feature extraction and fusion modules. Following [7, 26, 51], we first use ResNet50 to extract the static feature of each frame to form a static representation sequence _X_ = _{xt ∈_ R[2048] _[×][H]_[1] _[×][W]_[1] _}[T] t_ =1[.][The][extracted] _[X]_[is][then][fed][into][our] Multi-scale Feature Fusion module (MFF) to generate the fusion feature sequences _G_ = _{gt}[T] t_ =1[,][with][two-layer] Transformer blocks behind to learn their long-term temporal dependencies and yield the temporal feature sequence _Z_ = _{zt}[T] t_ =1[.][Finally, We use the mean feature of] _[ Z]_[as the] integrated feature representation of the mid-frame and produce final estimations with an IEF SMPL regressor [23]. 

**TopK-Mask and Learnable Mask.** We employ a TopK selection algorithm to generate high-pressure 0-1 masks for each pressure image (elements larger than K-largest value is set as 1). The mask, noted as _H[K]_ , will be fed into MFF as contour priors. Besides, we incorporate a learnable mask _H[LK]_ into our model, utilizing the initial pressure input _Ii_ and the TopK-Mask matrix _Hi[K]_ to learn an attention distribution that evaluates the contribution of features in the feature map. The learnable mask is computed as: 

_Hi[LK]_ = Softmax(Conv([ _Ii ⊙ Hi[K][, H] i[K]_[]))] (6) where _⊙_ is the Hadamard product. The product result will be stacked with the TopK-mask and fed into a 1-layer convolution layer and Softmax layer to generate the attention matrix _Hi[LK] ∈_ R _[H][×][W]_ . We aim to explicitly integrate these pressure distributions to enhance learnable masks’ quality. The K is set as 128 in PI-HMR, and we also conduct abla- 

## **4.1.2. Multi-Scale Feature Fusion Module** 

To exploit the characteristics of pressure images, our core insight lies in that both large-pressure regions and human joint projections are essential for model learning: large-pressure regions represent the primary contact areas between humans and environments, directly reflecting user’s posture and movement tendencies; 2D joint posi- 

27743 

**==> picture [224 x 143] intentionally omitted <==**

**----- Start of picture text -----**<br>
𝒙𝒙 𝒈𝒈 [𝒈𝒈]<br>Average Pooling<br>Down Sampling<br>2048 × 𝐻𝐻1 × 𝑊𝑊1 512 × 1<br>Joint<br>Regressor<br>Up Sampling 𝒈𝒈<br>𝒙𝒙 [𝒖] Joint-guided<br>= Sampling 256 × 12 C TransformerBlock 𝒈𝒈 [𝒍𝒍] C<br>256 × 𝐻𝐻× 𝑊𝑊 Pressure-guidedSampling 256 × K Ill 256 × 1 1024 × 1<br>P<br>P<br>𝒈𝒈 [𝒔𝒔]<br>Top K SoftmaxConv &  X Attention Pooling<br>256 × 𝐻𝐻× 𝑊𝑊 256 × 1<br>TopK-Mask Learnable Mask<br>C Tensor concat P Spatial positional embedding X Channel-wise multiplication<br>**----- End of picture text -----**<br>


Figure 5. **Framework of our multi-scale feature fusion module.** 

tions to discuss the selection of K in Tab. 4. 

**Auxiliary Joint Regressor.** We use an auxiliary joint regressor to provide 2D joints for the multi-scale feature extraction (shown in Fig. 5). The regressor takes the static feature _xi_ as input and returns the 2D positions of 12 joints in the pressure image, noted as _Ji_[2] _[D]_ . The 2D regressor will be trained in conjunction with the entire model. 

**Multi-Scale Feature Fusion.** We extract the global feature _gi[g]_[,][local][feature] _[g] i[l]_[,][and][sampling][feature] _[g] i[s]_[from][the] static feature _xi_ , without replying on the temporal consistency. Firstly for global feature, we apply average pooling and downsampling to the static features _xi ∈_ R[2048] _[×][H]_[1] _[×][W]_[1] to generate global representation _gi[g][∈]_[R][512][.] Subsequently, we perform dimension-upsampling on _xi_ to obtain upsampled feature _x[up] i ∈_ R[256] _[×][H][×][W]_ that aligned with the initial pressure input scale, facilitating us to apply spatial position embedding and feature sampling. For local features, we add _x[up] i_ to the spatial position map _Pi_ we have learned, multiply it point-wise with the Learnable Mask _Hi[LK]_ , and then subject it to AttentionPooling to derive the local features _gi[l][∈]_[R][256][.] 

As for the sampling features, we employ a feature sampling process on _x[up] i_ based on the pre-obtained TopKMasks and 12 2D keypoint positions obtained from a auxiliary 2D keypoint regressor and get a medium feature _gi[mid] ∈_ R[(] _[K]_[+12)] _[×]_[256] . After the same spatial position embedding, the medium feature will be input into a 1-layer Transformer layer to learn its spatial semantics, with the mean of the results serving as the sampling feature _gi[s][∈]_[R][256][.] 

Finally we get the fusion feature _gi ∈_ R[1024] by concatenating aforesaid global, local, and sampling features. 

## **4.1.3. Training Strategy** 

The overall loss function can be expressed as follows: 

**==> picture [200 x 9] intentionally omitted <==**

where _L_ SMPL and _L_ 3 _D_ presents the deviations between the estimated SMPL parameters and 3d joints with GTs, and _L_ 2 _D_ minimize errors in 2D joints for the auxiliary regressor. 

## **4.2. Encoder pre-train by cross-modal KD** 

We employ a cross-modal KD framework to pretrain our PI-HMR’s feature encoder, aiming at learning motion and shape priors from vision-based methods on paired pressureRGB images. Specifically, we implement a HMR [23] architecture as the student network _FS_ (with a ResNet50 as encoder and a IEF [23] SMPL regressor), and choose CLIFF (ResNet50) [30] as the teacher model _FT_ (a HMRbased network). During pre-training, we apply extra feature-based and response-based KD [15] to realize finegrained knowledge transfer. Given input pressure-RGBlabel groups ( _IP , IR, y_ ), and 4 pairs of hidden feature maps from _FT_ and _FS_ (ResNet50 has 4 residual blocks, so we extract the feature maps after each residual block), i.e., _MT_ from _FT_ and _MS_ from _FS_ , the loss function is: 

**==> picture [231 x 43] intentionally omitted <==**

where _Lpi_ is the same as Eq. (7), and _λ_ is the hyperparamter. After training and convergence, the ResNet50 encoder from _FS_ will be adopted as PI-HMR’s pre-trained static encoder and finetuned in the following training process. 

## **4.3. Test-Time Optimization** 

We also explore a TTO routine to further enhance prediction quality of PI-HMR. Considering that there hasn’t been a general 2D keypoint regressor for pressure images, we are inclined toward seeking an unsupervised, prior-based optimization strategy. We notice that humans exhibit similar movement patterns across various postural states ( _e.g_ ., timing, which hand to support, and leg movements). This inspires us to pre-learn such a motion habit as motion prior, playing as supplement cues to refine PI-HMR’s prediction. 

We apply a VQ-VAE as the motion prior learner. The selection is rooted in our assumption that the distribution of bed-bound movements is rather constrained. In that case, for a noised motion prediction, VQ-VAE could match it to the closest pattern, thereby re-generating habit-based results. The VQ-VAE is based on Transformer blocks and show similar architecture with [13]. During training, we only auto-reconstruct the pose sequences ( _θ_ in SMPL). More details are provided in Supplementary Materials. 

The VQ-VAE will act as the only motion prior and supervision in our TTO routine. For terminological convenience, given a VQ-VAE M and PI-HMR initial predictions Θ[0] = _{θ_ 1[0] _[, ...θ] T_[0] _[}]_[, the] _[ i][th]_[iteration objectives follows:] 

**==> picture [218 x 11] intentionally omitted <==**

_Lm_ is the SMPL and joint error term, and _Lsm_ is the smooth loss. The result of _ith_ iteration will be input into M and optimized in the _i_ + 1 _th_ iteration. The TTO will help maintain 

27744 

|Method|Input|Modalities|MPJPE<br>PA-MPJPE<br>MPVE<br>ACC-ERR|
|---|---|---|---|
|HMR [23]<br>HMR-KD<br>BodyMap-WS[46]|single|Pressure|75.06<br>57.97<br>89.11<br>31.52<br>66.30<br>52.41<br>83.01<br>24.41<br>71.48<br>**40.91**<br>80.08<br>27.98|
|TCMR [7]<br>MPS-NET [51]<br>PI-Mesh[52]|sequence||64.37<br>46.76<br>74.66<br>20.12<br>160.59<br>112.12<br>187.13<br>28.73<br>76.47<br>54.65<br>90.54<br>21.86|
|PI-HMR (ours)<br>PI-HMR + KD (ours)<br>PI-HMR + TTO (ours)<br>PI-HMR + KD + TTO (ours)|||59.46<br>44.53<br>69.92<br>**9.12**<br>57.13<br>42.98<br>67.22<br>9.84<br>57.76<br>43.31<br>67.76<br>9.83<br>**55.50**<br>41.81<br>**65.15**<br>9.96|



Table 1. **Overall results of PI-HMR with SOTA methods** 

**==> picture [491 x 132] intentionally omitted <==**

**----- Start of picture text -----**<br>
Ref. Input Cliff PI-Mesh PI-HMR Ref. Input Cliff PI-Mesh PI-HMR Ref. Input Cliff PI-Mesh PI-HMR<br>J eG (iGeayaed jena<br>SBI) BEE) SRE<br>**----- End of picture text -----**<br>


Figure 6. **Qualitative visualization for PI-HMR.** PI-HMR and PI-Mesh’s results are generated by pressure images, while CLIFF’s outputs are generated by RGB images for cross-modal comparison. Predictions are rendered on RGB images for comparison convenience 

a balance between initial PI-HMR outputs and the reconstruction by VQ-VAE, thus learning robust motion priors. 

|GF<br>LF<br>SF-P<br>SF-K|MPJPE<br>PA-MPJPE|
|---|---|
|✓<br>✓<br>✓<br>✓<br>✓<br>✓<br>✓<br>✓<br>✓|57.84<br>43.18<br>59.26<br>45.27<br>58.31<br>43.92<br>59.03<br>44.45<br>62.23<br>44.91<br>58.48<br>44.27<br>**57.13**<br>**42.98**|
|✓<br>✓<br>✓<br>✓<br>✓<br>✓<br>✓<br>✓<br>✓<br>✓||



## **5. Experiments** 

We evaluate PI-HMR on the TIP dataset. Following [52], we choose the second-to-last group of each subject as the val. set, the last group of each subject as the test set, and the remains as the training set. For evaluation, We use standard evaluation metrics including MPJPE (without pelvis alignment), PA-MPJPE, MPVE for shape errors, and Acceleration errors (ACC-ERR) to evaluate smoothness. The first three metrics are measured in millimeters ( _mm_ ), and the rest are measured in _mm/s_[2] . 

Table 2. **Ablations for model structures** . GF, LF, SF-P, SF-K are the global features, local features, sampling features from highpressure areas and joints, respectively. 

ment, while maintaining comparable ACC-ERR compared with SOTA approaches. Moreover, our introduced crossmodal KD and TTO strategy further improve the robustness of PIHMR, bringing 2.33mm and 1.7mm MPJPE improvements compared with basic structure. In particular, the TTO strategy, as an unsupervised, entirely prior-based optimization strategy, demonstrates the effectiveness of learning and refinement based on user habits. We provide visual comparisons between CLIFF, PI-Mesh and PI-HMR in Fig. 6. 

We compare our model with previous SOTAs and visonbased classic structures, including: HMR [23] and HMRKD (HMR structure with and without cross-modal KD), BodyMap-WS [46], TCMR [7], MPS-NET [51], and PIMesh [52]. All methods are re-trained on TIP with our re-generated SMPL p-GTs, and follow the same training setups with PI-HMR. We provide detailed implementation details of these approaches and PI-HMR in Sup. Mat. 

## **5.2. Ablations for PI-HMR** 

In this section, we present various ablation studies to fully explore the best setup of PI-HMR. We select PI-HMR as shorthand to mean PI-HMR + KD, without the TTO routine, as the basic model for evaluation. All models are trained and tested with the same data as PI-HMR. 

## **5.1. Overall Results for PI-HMR** 

We present quantitative evaluations in Tab. 1. Our methods outperform all image or sequence-based methods, presenting about 17.01mm MPJPE decrease compared to PIMesh and also outperforms SOTA vision-based architecture HMR, TCMR with 15.6mm, 4.91mm MPJPE improve- 

**Model Structures.** In Tab. 2, we summarize the results with different feature combinations in the MFF mod- 

27745 

|SamplingMethod|MPJPE<br>PA-MPJPE|
|---|---|
|Top 8<br>Top 32<br>Top 128<br>Top 256|58.62<br>44.42<br>57.66<br>43.48<br>**57.13**<br>**42.98**<br>58.64<br>44.65|



Table 3. **Ablations for the K selection in TopK algorithm.** 

|able 3. **Ablations for the K selec**|**tion in TopK algorith**|
|---|---|
|Method|MPJPE<br>PA-MPJPE|
|w/o. Learnable Masks<br>w/o. Spatial Position Embedding<br>w/o. AttentionPooling|60.95<br>46.27<br>60.65<br>46.28<br>59.21<br>45.08|
|All|**57.13**<br>**42.98**|
|Table 4. **Ablations for other components in MFF.**<br>GT<br>Output-KD<br>Feat.-KD<br>MPJPE<br>PA-MPJPE<br>✓<br>75.06<br>57.97<br>✓<br>✓<br>77.86<br>59.41<br>✓<br>✓<br>67.34<br>52.16<br>✓<br>✓<br>✓<br>**66.3**<br>**52.41**||
||MPJPE<br>PA-MPJPE|
||75.06<br>57.97<br>77.86<br>59.41<br>67.34<br>52.16<br>**66.3**<br>**52.41**|



Table 5. **Ablations for cross-modal KD** . GT, Output-KD, and Feat-KD represent supervision with GTs, CLIFF’s outputs, and CLIFF’s hidden feature maps, respectively. 

ule. The method that integrates all branches surpasses other setups. Notably, we observe accuracy drops when sampling features are solely sampled from high-pressure areas, without joints. This could be attributed to the model’s tendency to focus more on high pressure, neglecting the local distribution in boardline areas and low-pressure regions related with joints, thereby failing due to information ambiguity. 

**Top-K Sampling.** We explore the rational selection K for the high-pressure masks in Tab. 3. With an increase number of sampling points, the model’s performance initially improves and then declines when K is 256. This implies that the model seeks a balance in multi-feature fusion: more sampling points entail more abundant contact and contour information and a broader field of perception, but bringing in redundancy and noises. 

**Other Components in MFF.** We also conducted experiments to evaluate three essential modules including AttentionPooling for local features, learnable masks and spatial position embedding in MFF, as shown in Tab. 4. Our results suggest that these components provide strong priors for supervision and significantly improve the prediction accuracy. 

**Ablations for KD.** We conduct experiments to evaluate cross-modal KD. Tab. 5 shows that feature-based transfer plays a pivotal role in enhancing the performance, while CLIFF’s results might, to some extent, misguide the learning of HMR, due to domain gaps (CLIFF’s encoder is pretrained on ImageNet). When both supervisions coexist, HMR could learn the complete cognitive thought-chain of CLIFF, leading to refinement in predictions. 

## **5.3. Results for SMPLify-IB** 

Tab. 6 provides the evaluation of p-GTs generated by SMPLify-IB. Besides the 2D projection errors and accel- 

||2D MPJPE<br>Limb height|
|---|---|
|CLIFF|25.20<br>-|
|TIP|14.02<br>142.84|
|SMPLify-IB|**9.65**<br>**66.68**|



Table 6. **Qualitative results for SMPLify-IB, compared with the p-GTs in TIP, and CLIFF’s outputs** . We calculate the 2D projection errors (in pixels), and the average height of limbs marked as stationary relative to the bed. 

||recall<br>precision<br>accuracy<br>time|
|---|---|
|SMPLify-XMC|100%<br>100%<br>100%<br>22.62s|
|Ours|70.93%<br>80.64%<br>98.32%<br>0.42s|
|Ours (ds 1/3)|65.66%<br>73.59%<br>98.03%<br>0.036s|



Table 7. **Comparisons between our penetration detection algorithm with SMPLify-XMC.** Time means time consumption in an iteration when deploying detection algorithms in our optimization. ’ds 1/3’ means downsample SMPL vertices to their 1/3 scales. 

eration metrics, we introduce the static limb height as an objective assessment of our refinement in implausible limb lifts. Given the prevalence of limbs placed on other body parts within TIP, this metric can only serve as a rough estimate under limited self-penetration premise. We provide visual results in the Sup. Mat. to present our enhancements. 

We use SMPLify-XMC’s detection results as the GTs and conduct comparison experiments to evaluate our lightweight self-penetration detection algorithm in Tab. 7. The experiment run on the first group of the TIP dataset. For each batch with 128 images, we integrate both detection algorithms in our optimization routine, record the runtime for each iteration (1000 iterations for a batch) and calculate the accuracy, precision, and recall of the detection. Compared with SMPLify-XMC, our detection module achieves 53.9 times faster while maintaining a detection accuracy of 98.32%. We also implement a more lightweight version by downsampling the SMPL vertices into their 1/3 scale. The downsampled version further yields a more than tenfold increase in speed, accompanied by limited precision decrease. 

## **6. Conclusion** 

In this work, we present a general framework for inbed human shape estimation with pressure images, bridging from pseudo-label generation to algorithm design. For label generation, we present SMPLify-IB, a low-cost monocular optimization approach to generate SMPL p-GTs for in-bed scenes. By introducing gravity constraints and a lightweight but efficient self-penetration detection module, we regenerate higher-quality SMPL labels for a public dataset TIP. For model design, we introduce PI-HMR, a pressure-based HPS network to predict in-bed motions from pressure sequences. By fusing pressure distribution and spatial priors, accompanied with KD and TTO exploration, PI-HMR outperforms previous methods. Results verify the feasibility of enhancing model’s performance by exploiting pressure’s nature. 

27746 

**Acknowledgements:** We thank the anonymous reviewers for their suggestions. This work is supported by the National Natural Science Foundation of China under Grant No. 62072420. 

## **References** 

- [1] Felix Achilles, Alexandru-Eugen Ichim, Huseyin Coskun, Federico Tombari, Soheyl Noachtar, and Nassir Navab. Patient mocap: Human pose estimation under blanket occlusion for hospital monitoring applications. In _MICCAI_ , pages 491–499. Springer, 2016. 3 

- [2] Anurag Arnab, Carl Doersch, and Andrew Zisserman. Exploiting temporal context for 3d human pose estimation in the wild. In _CVPR_ , pages 3395–3404, 2019. 3 

- [3] Federica Bogo, Angjoo Kanazawa, Christoph Lassner, Peter Gehler, Javier Romero, and Michael J Black. Keep it smpl: Automatic estimation of 3d human pose and shape from a single image. In _ECCV_ , pages 561–578. Springer, 2016. 3, 4, 5 

- [4] Zhe Cao, Tomas Simon, Shih-En Wei, and Yaser Sheikh. Realtime multi-person 2d pose estimation using part affinity fields. In _CVPR_ , pages 7291–7299, 2017. 3 

- [5] Liqiong Chang, Jiaqi Lu, Ju Wang, Xiaojiang Chen, Dingyi Fang, Zhanyong Tang, Petteri Nurmi, and Zheng Wang. Sleepguard: Capturing rich sleep information using smartwatch sensing data. _Proceedings of the ACM on Interactive, Mobile, Wearable and Ubiquitous Technologies_ , 2(3):1–34, 2018. 1 

- [6] Wenqiang Chen, Yexin Hu, Wei Song, Yingcheng Liu, Antonio Torralba, and Wojciech Matusik. Cavatar: Real-time human activity mesh reconstruction via tactile carpets. _Proceedings of the ACM on Interactive, Mobile, Wearable and Ubiquitous Technologies_ , 7(4):1–24, 2024. 3 

- [7] Hongsuk Choi, Gyeongsik Moon, Ju Yong Chang, and Kyoung Mu Lee. Beyond static features for temporally consistent 3d human pose and shape from a video. In _CVPR_ , pages 1964–1973, 2021. 2, 3, 5, 7 

- [8] Henry M Clever, Ariel Kapusta, Daehyung Park, Zackory Erickson, Yash Chitalia, and Charles C Kemp. 3d human pose estimation on a configurable bed from a pressure image. In _2018 IEEE/RSJ International Conference on Intelligent Robots and Systems (IROS)_ , pages 54–61. IEEE, 2018. 1, 3 

- [9] Henry M Clever, Zackory Erickson, Ariel Kapusta, Greg Turk, Karen Liu, and Charles C Kemp. Bodies at rest: 3d human pose and shape estimation from a pressure image using synthetic data. In _CVPR_ , pages 6215–6224, 2020. 1, 2, 3 

- [10] Vandad Davoodnia and Ali Etemad. Human pose estimation from ambiguous pressure recordings with spatio-temporal masked transformers. In _ICASSP 2023-2023 IEEE International Conference on Acoustics, Speech and Signal Processing (ICASSP)_ , pages 1–5. IEEE, 2023. 3 

- [11] Jia Deng, Wei Dong, Richard Socher, Li-Jia Li, Kai Li, and Li Fei-Fei. Imagenet: A large-scale hierarchical image database. In _CVPR_ , pages 248–255. Ieee, 2009. 2 

- [12] Sai Kumar Dwivedi, Yu Sun, Priyanka Patel, Yao Feng, and Michael J Black. Tokenhmr: Advancing human mesh recov- 

ery with a tokenized pose representation. In _CVPR_ , pages 1323–1333, 2024. 3 

- [13] Han Feng, Wenchao Ma, Quankai Gao, Xianwei Zheng, Nan Xue, and Huijuan Xu. Stratified avatar generation from sparse observations. In _CVPR_ , pages 153–163, 2024. 6 

- [14] Shubham Goel, Georgios Pavlakos, Jathushan Rajasegaran, Angjoo Kanazawa, and Jitendra Malik. Humans in 4d: Reconstructing and tracking humans with transformers. In _CVPR_ , pages 14783–14794, 2023. 3 

- [15] Jianping Gou, Baosheng Yu, Stephen J Maybank, and Dacheng Tao. Knowledge distillation: A survey. _IJCV_ , 129 (6):1789–1819, 2021. 6 

- [16] Robert Grimm, Sebastian Bauer, Johann Sukkau, Joachim Hornegger, and G¨unther Greiner. Markerless estimation of patient orientation, posture and pose using range and pressure imaging: For automatic patient setup and scanner initialization in tomographic imaging. _International journal of computer assisted radiology and surgery_ , 7:921–929, 2012. 3 

- [17] Mohamed Hassan, Vasileios Choutas, Dimitrios Tzionas, and Michael J Black. Resolving 3d human pose ambiguities with 3d scene constraints. In _CVPR_ , pages 2282–2292, 2019. 3 

- [18] Geoffrey Hinton. Distilling the knowledge in a neural network. _arXiv preprint arXiv:1503.02531_ , 2015. 2 

- [19] Enamul Hoque, Robert F Dickerson, and John A Stankovic. Monitoring body positions and movements during sleep using wisps. In _Wireless Health 2010_ , pages 44–53. 2010. 1 

- [20] Yinghao Huang, Omid Taheri, Michael J Black, and Dimitrios Tzionas. Intercap: Joint markerless 3d tracking of humans and objects in interaction from multi-view rgb-d images. _IJCV_ , pages 1–16, 2024. 3 

- [21] Alec Jacobson, Ladislav Kavan, and Olga Sorkine-Hornung. Robust inside-outside segmentation using generalized winding numbers. _TOG_ , 32(4):1–12, 2013. 4 

- [22] Hanbyul Joo, Natalia Neverova, and Andrea Vedaldi. Exemplar fine-tuning for 3d human model fitting towards in-thewild 3d human pose estimation. In _3DV_ , pages 42–52. IEEE, 2021. 3 

- [23] Angjoo Kanazawa, Michael J Black, David W Jacobs, and Jitendra Malik. End-to-end recovery of human shape and pose. In _CVPR_ , pages 7122–7131, 2018. 3, 5, 6, 7 

- [24] Angjoo Kanazawa, Jason Y Zhang, Panna Felsen, and Jitendra Malik. Learning 3d human dynamics from video. In _CVPR_ , pages 5614–5623, 2019. 3 

- [25] Manuel Kaufmann, Jie Song, Chen Guo, Kaiyue Shen, Tianjian Jiang, Chengcheng Tang, Juan Jos´e Z´arate, and Otmar Hilliges. Emdb: The electromagnetic database of global 3d human pose and shape in the wild. In _CVPR_ , pages 14632– 14643, 2023. 3 

- [26] Muhammed Kocabas, Nikos Athanasiou, and Michael J Black. Vibe: Video inference for human body pose and shape estimation. In _CVPR_ , pages 5253–5263, 2020. 3, 5 

- [27] Muhammed Kocabas, Chun-Hao P Huang, Otmar Hilliges, and Michael J Black. Pare: Part attention regressor for 3d human body estimation. In _CVPR_ , pages 11127–11137, 2021. 3 

27747 

- [28] Muhammed Kocabas, Chun-Hao P Huang, Joachim Tesch, Lea M¨uller, Otmar Hilliges, and Michael J Black. Spec: Seeing people in the wild with an estimated camera. In _ICCV_ , pages 11035–11045, 2021. 

- [29] Nikos Kolotouros, Georgios Pavlakos, Michael J Black, and Kostas Daniilidis. Learning to reconstruct 3d human pose and shape via model-fitting in the loop. In _CVPR_ , pages 2252–2261, 2019. 

- [30] Zhihao Li, Jianzhuang Liu, Zhensong Zhang, Songcen Xu, and Youliang Yan. Cliff: Carrying location information in full frames into human pose and shape estimation. In _ECCV_ , pages 590–606. Springer, 2022. 2, 3, 6 

- [31] Jing Lin, Ailing Zeng, Haoqian Wang, Lei Zhang, and Yu Li. One-stage 3d whole-body mesh recovery with component aware transformer. In _CVPR_ , pages 21159–21168, 2023. 3 

- [32] Shuangjun Liu and Sarah Ostadabbas. Seeing under the cover: A physics guided learning approach for in-bed pose estimation. In _MICCAI_ , pages 236–245. Springer, 2019. 3 

- [33] Shuangjun Liu, Yu Yin, and Sarah Ostadabbas. In-bed pose estimation: Deep learning with shallow dataset. _IEEE journal of translational engineering in health and medicine_ , 7: 1–12, 2019. 3 

- [34] Shuangjun Liu, Xiaofei Huang, Nihang Fu, Cheng Li, Zhongnan Su, and Sarah Ostadabbas. Simultaneouslycollected multimodal lying pose dataset: Enabling in-bed human pose monitoring. _TPAMI_ , 45(1):1106–1118, 2022. 2, 3 

- [35] Matthew Loper, Naureen Mahmood, Javier Romero, Gerard Pons-Moll, and Michael J Black. Smpl: A skinned multiperson linear model. In _Seminal Graphics Papers: Pushing the Boundaries, Volume 2_ , pages 851–866. 2023. 1, 3 

- [36] Yiyue Luo, Yunzhu Li, Michael Foshey, Wan Shou, Pratyusha Sharma, Tom´as Palacios, Antonio Torralba, and Wojciech Matusik. Intelligent carpet: Inferring 3d human pose from tactile signals. In _CVPR_ , pages 11255–11265, 2021. 3 

- [37] Naureen Mahmood, Nima Ghorbani, Nikolaus F Troje, Gerard Pons-Moll, and Michael J Black. Amass: Archive of motion capture as surface shapes. In _ICCV_ , pages 5442–5451, 2019. 2 

- [38] Lea Muller, Ahmed AA Osman, Siyu Tang, Chun-Hao P Huang, and Michael J Black. On self-contact and human pose. In _CVPR_ , pages 9990–9999, 2021. 2, 3, 4 

- [39] Lea M¨uller, Vickie Ye, Georgios Pavlakos, Michael Black, and Angjoo Kanazawa. Generative proxemics: A prior for 3d social interaction from images. In _CVPR_ , pages 9687– 9697, 2024. 3 

- [40] Georgios Pavlakos, Vasileios Choutas, Nima Ghorbani, Timo Bolkart, Ahmed AA Osman, Dimitrios Tzionas, and Michael J Black. Expressive body capture: 3d hands, face, and body from a single image. In _CVPR_ , pages 10975– 10985, 2019. 3 

- [41] Xiaolong Shen, Zongxin Yang, Xiaohan Wang, Jianxin Ma, Chang Zhou, and Yi Yang. Global-to-local modeling for video-based 3d human pose and shape estimation. In _CVPR_ , pages 8887–8896, 2023. 3 

- [42] Soshi Shimada, Vladislav Golyanik, Patrick P´erez, and Christian Theobalt. Decaf: Monocular deformation capture for face and hand interactions. _TOG_ , 42(6):1–16, 2023. 3 

- [43] Soyong Shin, Juyong Kim, Eni Halilaj, and Michael J Black. Wham: Reconstructing world-grounded humans with accurate 3d motion. In _CVPR_ , pages 2070–2080, 2024. 

- [44] Yu-Pei Song, Xiao Wu, Zhaoquan Yuan, Jian-Jun Qiao, and Qiang Peng. Posturehmr: Posture transformation for 3d human mesh recovery. In _CVPR_ , pages 9732–9741, 2024. 3 

- [45] Sanjay Subramanian, Evonne Ng, Lea M¨uller, Dan Klein, Shiry Ginosar, and Trevor Darrell. Pose priors from language models. _arXiv preprint arXiv:2405.03689_ , 2024. 3 

- [46] Abhishek Tandon, Anujraaj Goyal, Henry M Clever, and Zackory Erickson. Bodymap-jointly predicting body mesh and 3d applied pressure map for people in bed. In _CVPR_ , pages 2480–2489, 2024. 1, 2, 3, 7 

- [47] Aaron Van Den Oord, Oriol Vinyals, et al. Neural discrete representation learning. _NIPS_ , 30, 2017. 2 

- [48] Tom Van Wouwe, Seunghwan Lee, Antoine Falisse, Scott Delp, and C Karen Liu. Diffusionposer: Real-time human motion reconstruction from arbitrary sparse sensors using autoregressive diffusion. In _CVPR_ , pages 2513–2523, 2024. 3 

- [49] Timo Von Marcard, Roberto Henschel, Michael J Black, Bodo Rosenhahn, and Gerard Pons-Moll. Recovering accurate 3d human pose in the wild using imus and a moving camera. In _ECCV_ , pages 601–617, 2018. 1 

- [50] Yufu Wang and Kostas Daniilidis. Refit: Recurrent fitting network for 3d human recovery. In _CVPR_ , pages 14644– 14654, 2023. 3 

- [51] Wen-Li Wei, Jen-Chun Lin, Tyng-Luh Liu, and HongYuan Mark Liao. Capturing humans in motion: Temporalattentive 3d human pose and shape estimation from monocular video. In _CVPR_ , pages 13211–13220, 2022. 3, 5, 7 

- [52] Ziyu Wu, Fangting Xie, Yiran Fang, Zhen Liang, Quan Wan, Yufan Xiong, and Xiaohui Cai. Seeing through the tactile: 3d human shape estimation from temporal in-bed pressure images. _Proceedings of the ACM on Interactive, Mobile, Wearable and Ubiquitous Technologies_ , 8(2):1–39, 2024. 2, 3, 5, 7 

- [53] Yufei Xu, Jing Zhang, Qiming Zhang, and Dacheng Tao. Vitpose: Simple vision transformer baselines for human pose estimation. 35:38571–38584, 2022. 3 

- [54] Hongwei Yi, Hualin Liang, Yifei Liu, Qiong Cao, Yandong Wen, Timo Bolkart, Dacheng Tao, and Michael J Black. Generating holistic 3d human motion from speech. In _CVPR_ , pages 469–480, 2023. 3 

- [55] Yu Yin, Joseph P Robinson, and Yun Fu. Multimodal in-bed pose and shape estimation under the blankets. In _MM_ , pages 2411–2419, 2022. 2, 3 

- [56] Yingxuan You, Hong Liu, Ti Wang, Wenhao Li, Runwei Ding, and Xia Li. Co-evolution of pose and mesh for 3d human body estimation from video. In _ICCV_ , pages 14963– 14973, 2023. 3 

- [57] Rasoul Yousefi, Sarah Ostadabbas, Miad Faezipour, Masoud Farshbaf, Mehrdad Nourani, Lakshman Tamil, and Matthew Pompeo. Bed posture classification for pressure ulcer prevention. In _2011 Annual International Conference of the IEEE Engineering in Medicine and Biology Society_ , pages 7175–7178. IEEE, 2011. 1 

27748 

- [58] Dongquan Zhang, Zhen Liang, Yuchen Wu, Fangting Xie, Guanghua Xu, Ziyu Wu, and Xiaohui Cai. Learn to infer human poses using a full-body pressure sensing garment. _IEEE Sensors Journal_ , 2024. 3 

- [59] Hongwen Zhang, Yating Tian, Xinchi Zhou, Wanli Ouyang, Yebin Liu, Limin Wang, and Zhenan Sun. Pymaf: 3d human pose and shape regression with pyramidal mesh alignment feedback loop. In _CVPR_ , pages 11446–11456, 2021. 3 

- [60] He Zhang, Shenghao Ren, Haolei Yuan, Jianhui Zhao, Fan Li, Shuangpeng Sun, Zhenghao Liang, Tao Yu, Qiu Shen, and Xun Cao. Mmvp: A multimodal mocap dataset with vision and pressure sensors. In _CVPR_ , pages 21842–21852, 2024. 3 

- [61] Bo Zhou, Daniel Geissler, Marc Faulhaber, Clara Elisabeth Gleiss, Esther Friederike Zahn, Lala Shakti Swarup Ray, David Gamarra, Vitor Fortes Rey, Sungho Suh, Sizhen Bian, et al. Mocapose: Motion capturing with textile-integrated capacitive sensors in loose-fitting smart garments. _Proceedings of the ACM on Interactive, Mobile, Wearable and Ubiquitous Technologies_ , 7(1):1–40, 2023. 3 

27749 

