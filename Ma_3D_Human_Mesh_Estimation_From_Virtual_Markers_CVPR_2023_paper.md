This CVPR paper is the Open Access version, provided by the Computer Vision Foundation. Except for this watermark, it is identical to the accepted version; the final published version of the proceedings is available on IEEE Xplore. 

# **3D Human Mesh Estimation from Virtual Markers** 

Xiaoxuan Ma[1] Jiajun Su[1] Chunyu Wang[3][*] Wentao Zhu[1] Yizhou Wang[1, 2, 4] 

1 School of Computer Science, Center on Frontiers of Computing Studies, Peking University 

> 2 Inst. for Artificial Intelligence, Peking University 

3 Microsoft Research Asia 

> 4 Nat’l Eng. Research Center of Visual Technology 

{maxiaoxuan, sujiajun, wtzhu, yizhou.wang}@pku.edu.cn, chnuwa@microsoft.com 

## **Abstract** 

_Inspired by the success of volumetric 3D pose estimation, some recent human mesh estimators propose to estimate 3D skeletons as intermediate representations, from which, the dense 3D meshes are regressed by exploiting the mesh topology. However, body shape information is lost in extracting skeletons, leading to mediocre performance. The advanced motion capture systems solve the problem by placing dense physical markers on the body surface, which allows to extract realistic meshes from their non-rigid motions. However, they cannot be applied to wild images without markers. In this work, we present an intermediate representation, named virtual markers, which learns 64 landmark keypoints on the body surface based on the large-scale mocap data in a generative style, mimicking the effects of physical markers. The virtual markers can be accurately detected from wild images and can reconstruct the intact meshes with realistic shapes by simple interpolation. Our approach outperforms the state-of-the-art methods on three datasets. In particular, it surpasses the existing methods by a notable margin on the SURREAL dataset, which has diverse body shapes. Code is available at https: //github.com/ShirleyMaxx/VirtualMarker._ 

**==> picture [173 x 9] intentionally omitted <==**

**----- Start of picture text -----**<br>
Image  Pose2Mesh Ours GT<br>**----- End of picture text -----**<br>


Figure 1. Mesh estimation results on four examples with different body shapes. Pose2Mesh [7] which uses 3D skeletons as the intermediate representation fails to predict accurate shapes. Our virtual marker-based method obtains accurate estimates. 

## **1. Introduction** 

3D human mesh estimation aims to estimate the 3D positions of the mesh vertices that are on the body surface. The task has attracted a lot of attention from the computer vision and computer graphics communities [3, 10, 18, 24, 26, 29, 34, 36, 41, 49] because it can benefit many applications such as virtual reality [14]. Recently, the deep learning-based methods [7, 18, 28] have significantly 

> *Corresponding author 

advanced the accuracy on the benchmark datasets. 

The pioneer methods [18, 49] propose to regress the pose and shape parameters of the mesh models such as SMPL [35] directly from images. While straightforward, their accuracy is usually lower than the state-of-the-arts. The first reason is that the mapping from the image features to the model parameters is highly non-linear and suffers from image-model misalignment [28]. Besides, existing mesh datasets [15, 27, 37, 52] are small and limited to simple labo- 

534 

ratory environments due to the complex capturing process. The lack of sufficient training data severely limits its performance. 

Recently, some works [25, 38] begin to formulate mesh estimation as a dense 3D keypoint detection task inspired by the success of volumetric pose estimation [42, 43, 45, 48, 57, 63]. For example, in [25, 38], the authors propose to regress the 3D positions of all vertices. However, it is computationally expensive because it has more than several thousand vertices. Moon and Lee [38] improve the efficiency by decomposing the 3D heatmaps into multiple 1D heatmaps at the cost of mediocre accuracy. Choi _et al_ . [7] propose to first detect a sparser set of skeleton joints in the images, from which the dense 3D meshes are regressed by exploiting the mesh topology. The methods along this direction have attracted increasing attention [7, 28, 53] due to two reasons. First, the proxy task of 3D skeleton estimation can leverage the abundant 2D pose datasets which notably improves the accuracy. Second, mesh regression from the skeletons is efficient. However, important information about the body shapes is lost in extracting the 3D skeletons, which is largely overlooked previously. As a result, different types of body shapes, such as lean or obese, cannot be accurately estimated (see Figure 1). 

The professional marker-based motion capture (mocap) method MoSh [34] places physical markers on the body surface and explore their subtle non-rigid motions to extract meshes with accurate shapes. However, the physical markers limit the approach to be used in laboratory environments. We are inspired to think whether we can identify a set of landmarks on the mesh as virtual markers, _e.g_ ., elbow and wrist, that can be detected from wild images, and allow to recover accurate body shapes? The desired virtual markers should satisfy several requirements. First, the number of markers should be much smaller than that of the mesh vertices so that we can use volumetric representations to efficiently estimate their 3D positions. Second, the markers should capture the mesh topology so that the intact mesh can be accurately regressed from them. Third, the virtual markers have distinguishable visual patterns so that they can be detected from images. 

In this work, we present a learning algorithm based on archetypal analysis [12] to identify a subset of mesh vertices as the virtual markers that try to satisfy the above requirements to the best extent. Figure 2 shows that the learned virtual markers coarsely outline the body shape and pose which paves the way for estimating meshes with accurate shapes. Then we present a simple framework for 3D mesh estimation on top of the representation as shown in Figure 3. It first learns a 3D keypoint estimation network based on [45] to detect the 3D positions of the virtual markers. Then we recover the intact mesh simply by interpolating them. The interpolation weights are pre-trained in the representation 

learning step and will be adjusted by a light network based on the prediction confidences of the virtual markers for each image. 

We extensively evaluate our approach on three benchmark datasets. It consistently outperforms the state-of-the-art methods on all of them. In particular, it achieves a significant gain on the SURREAL dataset [51] which has a variety of body shapes. Our ablation study also validates the advantages of the virtual marker representation in terms of recovering accurate shapes. Finally, the method shows decent generalization ability and generates visually appealing results for the wild images. 

## **2. Related work** 

## **2.1. Optimization-based mesh estimation** 

Before deep learning dominates this field, 3D human mesh estimation [2, 27, 34, 40, 58] is mainly optimizationbased, which optimizes the parameters of the human mesh models to match the observations. For example, Loper _et al_ . [34] propose MoSh that optimizes the SMPL parameters to align the mesh with the 3D marker positions. It is usually used to get GT 3D meshes for benchmark datasets because of its high accuracy. Later works propose to optimize the model parameters or mesh vertices based on 2D image cues [2, 11, 27, 40, 58]. They extract intermediate representations such as 2D skeletons from the images and optimize the mesh model by minimizing the discrepancy between the model projection and the intermediate representations such as the 2D skeletons. These methods are usually sensitive to initialization and suffer from local optimum. 

## **2.2. Learning-based mesh estimation** 

Recently, most works follow the learning-based framework and have achieved promising results. Deep networks [18, 24, 26, 36, 49] are used to regress the SMPL parameters from image features. However, learning the mapping from the image space to the parameter space is highly nonlinear [38]. In addition, they suffer from the misalignment between the meshes and image pixels [60]. These problems make it difficult to learn an accurate yet generalizable model. 

Some works propose to introduce proxy tasks to get intermediate representations first, hoping to alleviate the learning difficulty. In particular, intermediate representations of physical markers [59], IUV images [55,60–62], body part segmentation masks [23,27,39,50] and body skeletons [7,28,47,53] have been proposed. In particular, THUNDR [59] first estimates the 3D locations of physical markers from images and then reconstructs the mesh from the 3D markers. The physical markers can be interpreted as a simplified representation of body shape and pose. Although it is very accurate, it cannot be applied to wild images without markers. In contrast, body skeleton is a popular human representation 

535 

**==> picture [57 x 25] intentionally omitted <==**

**----- Start of picture text -----**<br>
Zoom in TLS_<br>**----- End of picture text -----**<br>


Figure 2. **Left:** The learned virtual markers (blue balls) in the back and front views. The grey balls mean they are invisible in the front view. The virtual markers act similarly to physical body markers and approximately outline the body shape. **Right:** Mesh estimation results by our approach, from left to right are input image, estimated 3D mesh overlayed on the image, and three different viewpoints showing the estimated 3D mesh with our intermediate predicted virtual markers (blue balls), respectively. 

that can be robustly detected from wild images. Choi _et al_ . [7] propose to first estimate the 3D skeletons, and then estimate the intact mesh from them. However, accurate body shapes are difficult to be recovered from the oversimplified 3D skeletons. 

Our work belongs to the learning-based class and is related to works that use physical markers or skeletons as intermediate representations. But different from them, we propose a novel intermediate representation, named _virtual markers_ , which is more expressive to reduce the ambiguity in pose and shape estimation than body skeletons and can be applied to wild images. 

## **3. Method** 

In this section, we describe the details of our approach. First, Section 3.1 introduces how we learn the virtual marker representation from mocap data. Then we present the overall framework for mesh estimation from an image in Section 3.2. At last, Section 3.3 discusses the loss functions and training details. 

## **3.1. The virtual marker representation** 

We represent a mesh by a vector of vertex positions **x** _∈_ R[3] _[M]_ where _M_ is the number of mesh vertices. Denote a mocap dataset such as [15] with _N_ meshes as _⌢_ **X** = [ **x** 1 _, ...,_ **x** _N_ ] _∈_ R[3] _[M][×][N]_ . To unveil the latent structure among vertices, we reshape it to **X** _∈_ R[3] _[N][×][M]_ with each column **x** _i ∈_ R[3] _[N]_ representing all possible positions of the _i_[th] vertex in the dataset [15]. 

The rank of **X** is smaller than _M_ because the mesh representation is smooth and redundant where some vertices can be accurately reconstructed by the others. While it seems natural to apply PCA [17] to **X** to compute the eigenvectors as virtual markers for reconstructing others, there is no guarantee that the virtual markers correspond to the mesh vertices, making them difficult to be detected from images. Instead, we aim to learn _K_ virtual markers **Z** = [ **z** 1 _, ...,_ **z** _K_ ] _∈_ R[3] _[N][×][K]_ that try to satisfy the follow- 

|Type|Formula|Reconst. Error (mm) _↓_|
|---|---|---|
|Original<br>Symmetric|_||_**X**_−_**XBA**_||_2<br>_F_<br>_||_**X**_−_**X**�**B**_sym_�_sym||_2<br>_F_|11.67<br>10.98|



Table 1. The reconstruction errors using the original and the symmetric sets of markers on the H3.6M dataset [15], respectively. The errors are small indicating that they are sufficiently expressive and can reconstruct all vertices accurately. 

ing two requirements to the greatest extent. First, they can accurately reconstruct the intact mesh **X** by their linear combinations: **X** = **ZA** , where **A** _∈_ R _[K][×][M]_ is a coefficient matrix that encodes the spatial relationship between the virtual markers and the mesh vertices. Second, they should have distinguishable visual patterns in images so that they can be easily detected from images. Ideally, they can be on the body surface as the meshes. 

We apply archetypal analysis [4, 12] to learn **Z** by minimizing a reconstruction error with two additional constraints: (1) each vertex **x** _i_ can be reconstructed by convex combinations of **Z** , and (2) each marker **z** _i_ should be convex combinations of the mesh vertices **X** : 

**==> picture [191 x 26] intentionally omitted <==**

where **A** = [ _**α**_ 1 _, ...,_ _**α** M_ ] _∈_ R _[K][×][M]_ , each _**α**_ resides in the simplex ∆ _K_ ≜ _{_ _**α** ∈_ R _[K]_ s _._ t _._ _**α** ⪰_ 0 and _||_ _**α** ||_ 1 = 1 _}_ , and **B** = [ _**β**_ 1 _, ...,_ _**β** K_ ] _∈_ R _[M][×][K]_ , _**β** j ∈_ ∆ _M_ . We adopt Active-set algorithm [4] to solve objective (1) and obtain the learned virtual markers **Z** = **XB** _∈_ R[3] _[N][×][K]_ . As shown in [4, 12], the two constraints encourage the virtual markers **Z** to unveil the latent structure among vertices, therefore they learn to be close to the extreme points of the mesh and located on the body surface as much as possible. 

**Post-processing.** Since human body is left-right symmetric, we adjust **Z** to reflect the property. We first replace each **z** _i ∈_ **Z** by its nearest vertex on the mesh and obtain **Z**[�] _∈_ R[3] _[×][K]_ . This step allows us to compute the left or right counterpart 

536 

**==> picture [496 x 172] intentionally omitted <==**

**----- Start of picture text -----**<br>
3D virtual marker estimation Matrix<br>. oe multiplication  —<br>Voxel position<br>Soft-argmax index<br>3D  3D virtual markers  𝐏 [!]<br>> > Estimator ee)<br>Input image  𝐈 3D heatmap 𝐇 [!] 3D mesh  𝐌 [!]<br>i a Updating oc<br>Network | | !𝐌 = !𝐏 ! !𝐀<br>Confidence Coefficient<br>score matrix  𝐀 [!]<br>Figure 3. Overview of our framework. Given an input image  I , it first estimates the 3D positions P [ˆ]  of the virtual markers. Then we update<br>the coefficient matrix A [ˆ]  based on the estimation confidence scores  C  of the virtual markers. Finally, the complete human mesh can be<br>simply recovered by linear multiplication M [ˆ]  = P [ˆ] A [ˆ] .<br>**----- End of picture text -----**<br>


of each marker. Then we replace the markers in the right body with the symmetric vertices in the left body and obtain the symmetric markers **Z**[�] _[sym] ∈_ R[3] _[×][K]_ . Finally we update **B** and **A** by minimizing _||_ **X** _−_ **XB**[�] _[sym]_[ �] _[sym] ||_[2] _F_[subject] to **Z**[�] _[sym]_ = **XB**[�] _[sym]_ . More details are elaborated in the supplementary. 

Figure 2 shows the virtual markers learned on the mocap dataset [15] after post-processing. They are similar to the physical markers and approximately outline the body shape which agrees with our expectations. They are roughly evenly distributed on the surface of the body, and some of them are located close to the body keypoints, which have distinguishable visual patterns to be accurately detected. Table 1 shows the reconstruction errors of using original markers **XB** and the symmetric markers **XB**[�] _[sym]_ . Both can reconstruct meshes accurately. 

## **3.2. Mesh estimation framework** 

On top of the virtual markers, we present a simple yet effective framework for end-to-end 3D human mesh estimation from a single image. As shown in Figure 3, it consists of two branches. The first branch uses a volumetric CNN [45] to estimate the 3D positions **P**[ˆ] of the markers, and the second branch reconstructs the full mesh **M**[ˆ] by predicting a coefficient matrix **A**[ˆ] : 

**==> picture [139 x 11] intentionally omitted <==**

We will describe the two branches in more detail. 

**3D marker estimation.** We train a neural network to estimate a 3D heatmap **H**[ˆ] = [ **H**[ˆ] 1 _, ...,_ **H**[ˆ] _K_ ] _∈_ R _[K][×][D][×][H][×][W]_ from an image. The heatmap encodes per-voxel likelihood of each marker. There are _D × H × W_ voxels in total which are used to discretize the 3D space. The 3D position **P**[ˆ] _z ∈_ R[3] of each marker is computed as the center of mass of the corresponding heatmap **H**[ˆ] _z_ [45] as follows: 

**==> picture [197 x 27] intentionally omitted <==**

The **P** ˆ = [ˆ **P** positions1 _,_ **P** ˆ 2 _, · · ·_ of _,_ **P** ˆ _K_ all]. markers are represented as 

**Interpolation.** Ideally, if we have accurate estimates for all virtual markers **P**[ˆ] , then we can recover the complete mesh by simply multiplying **P**[ˆ] with a fixed coefficient matrix **A**[�] _[sym]_ with sufficient accuracy as validated in Table 1. However, in practice, some markers may have large estimation errors because they may be occluded in the monocular setting. Note that this happens frequently. For example, the markers in the back will be occluded when a person is facing the camera. As a result, inaccurate markers positions may bring large errors to the final mesh if we directly multiply them with the fixed matrix **A**[�] _[sym]_ . 

Our solution is to rely more on those accurately detected markers. To that end, we propose to update the coefficient matrix based on the estimation confidence scores of the markers. In practice, we simply take the heatmap score at the estimated positions of each marker, _i.e_ . **H**[ˆ] _z_ ( **P**[ˆ] _z_ ), and feed them to a single fully-connected layer to obtain the coefficient **M** ˆ = **P** ˆ ˆ **A** . matrix **A**[ˆ] . Then the mesh is reconstructed by 

## **3.3. Training** 

We train the whole network end-to-end in a supervised way. The overall loss function is defined as: 

**==> picture [193 x 10] intentionally omitted <==**

**Virtual marker loss.** We define _Lvm_ as the _L_ 1 distance between the predicted 3D virtual markers **P**[ˆ] and the GT **P**[ˆ] _[∗]_ as follows: 

**==> picture [157 x 12] intentionally omitted <==**

Note that it is easy to get GT markers **P**[ˆ] _[∗]_ from GT meshes as stated in Section 3.1 without additional manual annotations. 

**Confidence loss.** We also require that the 3D heatmaps have reasonable shapes, therefore, the heatmap score at the 

537 

voxel containing the GT marker position **P**[ˆ] _[∗] z_[should have the] maximum value as in the previous work [16]: 

**==> picture [175 x 26] intentionally omitted <==**

**Mesh loss.** Following [38], we define _Lmesh_ as a weighted sum of four losses: 

- _Lmesh_ = _Lvertex_ + _Lpose_ + _Lnormal_ + _λeLedge._ (7) 

- **Vertex coordinate loss.** We adopt _L_ 1 loss between predicted 3D mesh coordinates **M**[ˆ] with GT mesh **M**[ˆ] _[∗]_ as: 

**==> picture [156 x 12] intentionally omitted <==**

- **Pose loss.** We use _L_ 1 loss between the 3D landmark joints regressed from mesh **M**[ˆ] _J_ and the GT joints **J**[ˆ] _[∗]_ as: 

**==> picture [154 x 12] intentionally omitted <==**

- where _J ∈_ R _[M][×][J]_ is a pre-defined joint regression matrix in SMPL model [2]. 

– **Surface losses.** To improve surface smoothness [54], we supervise the normal vector of a triangle face with GT normal vectors by _Lnormal_ and the edge length of the predicted mesh with GT length by _Ledge_ : 

**==> picture [204 x 57] intentionally omitted <==**

## **4.2. Implementation Details** 

We learn 64 virtual markers on the H3.6M [15] training set. We use the same set of markers for all datasets instead of learning a separate set on each dataset. Following [7, 18, 22,25,31,32,38,59], we conduct mix-training by using MPIINF-3DHP [37], UP-3D [27], and COCO [33] training set for experiments on the H3.6M and 3DPW datasets. We adapt a 3D pose estimator [45] with HRNet-W48 [44] as the image feature backbone for estimating the 3D virtual markers. We set the number of voxels in each dimension to be 64, _i.e_ . _D_ = _H_ = _W_ = 64 for 3D heatmaps. Following [18,25,38], we crop every single human region from the input image and resize it to 256 _×_ 256. We use Adam [21] optimizer to train the whole framework for 40 epochs with a batch size of 32. The learning rates for the two branches are set to 5 _×_ 10 _[−]_[4] and 1 _×_ 10 _[−]_[3] , respectively, which are decreased by half after the 30 _[th]_ epoch. Please refer to the supplementary for more details. 

## **4.3. Comparison to the State-of-the-arts** 

**Results on H3.6M.** Table 2 compares our approach to the state-of-the-art methods on the H3.6M dataset. Our method achieves competitive or superior performance. In particular, it outperforms the methods that use skeletons (Pose2Mesh [7], DSD-SATN [47]), body markers (THUNDR) [59], or IUV image [60, 62] as proxy representations, demonstrating the effectiveness of the virtual marker representation. 

**==> picture [15 x 9] intentionally omitted <==**

where _f_ and **n** ˆ _[∗] f_[denote a triangle face in the mesh and] its GT unit normal vector, respectively. **M**[ˆ] _i_ denote the _i[th]_ vertex of **M**[ˆ] . _[∗]_ denotes GT. 

## **4. Experiments** 

## **4.1. Datasets and metrics** 

**H3.6M [15].** We use (S1, S5, S6, S7, S8) for training and (S9, S11) for testing. As in [7, 18, 31, 32], we report MPJPE and PA-MPJPE for poses that are derived from the estimated meshes. We also report Mean Per Vertex Error (MPVE) for the whole mesh. 

**3DPW [52]** is collected in natural scenes. Following the previous works [23, 31, 32, 59], we use the train set of 3DPW to learn the model and evaluate on the test set. The same evaluation metrics as H3.6M are used. 

**SURREAL [51]** is a large-scale synthetic dataset with GT SMPL annotations and has diverse samples in terms of body shapes, backgrounds, _etc_ . We use its training set to train a model and evaluate the test split following [7]. 

**Results on 3DPW.** We compare our method to the state-of-the-art methods on the 3DPW dataset in Table 2. Our approach achieves state-of-the-art results among all the methods, validating the advantages of the virtual marker representation over the skeleton representation used in Pose2Mesh [7], DSD-SATN [47], and other representations like IUV image used in PyMAF [62]. In particular, our approach outperforms I2L-MeshNet [38], METRO [31], and Mesh Graphormer [32] by a notable margin, which suggests that virtual markers are more suitable and effective representations than detecting all vertices directly as most of them are not discriminative enough to be accurately detected. 

**Results on SURREAL.** This dataset has more diverse samples in terms of body shapes. The results are shown in Table 3. Our approach outperforms the state-of-the-art methods by a notable margin, especially in terms of MPVE. Figure 1 shows some challenging cases without cherry-picking. The skeleton representation loses the body shape information so the method [7] can only recover mean shapes. In contrast, our approach generates much more accurate mesh estimation results. 

538 

|Method<br>Intermediate<br>Representation|H3.6M|3DPW|
|---|---|---|
||MPVE_↓_<br>MPJPE_↓_<br>PA-MPJPE_↓_|MPVE_↓_<br>MPJPE_↓_<br>PA-MPJPE_↓_|
|_†_ Arnab_et al_. [1] CVPR’19<br>2D skeleton<br>_†_ HMMR [19] CVPR’19<br>-<br>_†_ DSD-SATN [47] ICCV’19<br>3D skeleton<br>_†_ VIBE [22] CVPR’20<br>-<br>_†_ TCMR [6] CVPR’21<br>-<br>_†_ MAED [53] ICCV’21<br>3D skeleton|-<br>77.8<br>54.3<br>-<br>-<br>56.9<br>-<br>59.1<br>42.4<br>-<br>65.9<br>41.5<br>-<br>62.3<br>41.1<br>-<br>56.3<br>38.7|-<br>-<br>72.2<br>139.3<br>116.5<br>72.6<br>-<br>-<br>69.5<br>99.1<br>82.9<br>51.9<br>102.9<br>86.5<br>52.7<br>92.6<br>79.1<br>45.7|
|SMPLify [2] ECCV’16<br>2D skeleton<br>HMR [18] CVPR’18<br>-<br>GraphCMR [25] CVPR’19<br>3D vertices<br>SPIN [24] ICCV’19<br>-<br>DenseRac [55] ICCV’19<br>IUV image<br>DecoMR [60] CVPR’20<br>IUV image<br>ExPose [9] ECCV’20<br>-<br>Pose2Mesh [7] ECCV’20<br>3D skeleton<br>I2L-MeshNet [38] ECCV’20<br>3D vertices<br>PC-HMR [36] AAAI’21<br>3D skeleton<br>HybrIK [28] CVPR’21<br>3D skeleton<br>METRO [31] CVPR’21<br>3D vertices<br>ROMP [46] ICCV’21<br>-<br>Mesh Graphormer [32] ICCV’21<br>3D vertices<br>PARE [23] ICCV’21<br>Segmentation<br>THUNDR [59] ICCV’21<br>3D markers<br>PyMaf [62] ICCV’21<br>IUV image<br>ProHMR [26] ICCV’21<br>-<br>OCHMR [20] CVPR’22<br>2D heatmap<br>3DCrowdNet [8] CVPR’22<br>3D skeleton<br>CLIFF [30] ECCV’22<br>-<br>FastMETRO [5] ECCV’22<br>3D vertices<br>VisDB [56] ECCV’22<br>3D vertices|-<br>-<br>82.3<br>96.1<br>88.0<br>56.8<br>-<br>-<br>50.1<br>-<br>-<br>41.1<br>-<br>76.8<br>48.0<br>-<br>60.6<br>39.3<br>-<br>-<br>-<br>85.3<br>64.9<br>46.3<br>65.1<br>55.7<br>41.1<br>-<br>-<br>-<br>65.7<br>54.4<br>34.5<br>-<br>54.0<br>36.7<br>-<br>-<br>-<br>-<br>51.2<br>34.5<br>-<br>-<br>-<br>-<br>55.0<br>39.8<br>-<br>57.7<br>40.5<br>-<br>-<br>41.2<br>-<br>-<br>-<br>-<br>-<br>-<br>-<br>**47.1**<br>32.7<br>-<br>52.2<br>33.7<br>-<br>51.0<br>34.5|-<br>-<br>-<br>152.7<br>130.0<br>81.3<br>-<br>-<br>70.2<br>116.4<br>96.9<br>59.2<br>-<br>-<br>-<br>-<br>-<br>-<br>-<br>93.4<br>60.7<br>106.3<br>88.9<br>58.3<br>110.1<br>93.2<br>57.7<br>108.6<br>87.8<br>66.9<br>86.5<br>74.1<br>45.0<br>88.2<br>77.1<br>47.9<br>108.3<br>91.3<br>54.9<br>87.7<br>74.7<br>45.6<br>88.6<br>74.5<br>46.5<br>88.0<br>74.8<br>51.5<br>110.1<br>92.8<br>58.9<br>-<br>-<br>59.8<br>107.1<br>89.7<br>58.3<br>98.3<br>81.7<br>51.5<br>81.2<br>69.0<br>43.0<br>84.1<br>73.5<br>44.6<br>85.5<br>73.5<br>44.9|
|**Ours**<br>Virtual marker|**58.0**<br>47.3<br>**32.0**|**77.9**<br>**67.5**<br>**41.3**|



Table 2. Comparison to the state-of-the-arts on H3.6M [15] and 3DPW [52] datasets. _[†]_ means using temporal cues. The methods are not strictly comparable because they may have different backbones and training datasets. We provide the numbers only to show proof-of-concept results. 

|Method<br>Intermediate<br>Representation|MPVE_↓_MPJPE_↓_PA-MPJPE_↓_|
|---|---|
|HMR [18] CVPR’18<br>-<br>BodyNet [50] ECCV’18<br>Skel. + Seg.<br>GraphCMR [25] CVPR’19<br>3D vertices<br>SPIN [24] ICCV’19<br>-<br>DecoMR [60] CVPR’20<br>IUV image<br>Pose2Mesh [7] ECCV’20<br>3D skeleton<br>PC-HMR [36] AAAI’21<br>3D skeleton<br>_∗_DynaBOA [13] TPAMI’22 -|85.1<br>73.6<br>55.4<br>65.8<br>-<br>-<br>103.2<br>87.4<br>63.2<br>82.3<br>66.7<br>43.7<br>68.9<br>52.0<br>43.0<br>68.8<br>56.6<br>39.6<br>59.8<br>51.7<br>37.9<br>70.7<br>55.2<br>34.0|
|**Ours**<br>Virtual marker|**44.7**<br>**36.9**<br>**28.9**|



Table 3. Comparison to the state-of-the-arts on SURREAL [51] dataset. _[∗]_ means training on the test split with 2D supervisions. “Skel. + Seg.” means using skeleton and segmentation together. 

## **4.4. Ablation study** 

**Virtual marker representation.** We compare our method to two baselines in Table 4. First, in baseline (a), we replace the virtual markers of our method with the skeleton representation. The rest are kept the same as ours (c). Our 

|No.|Intermediate<br>Representation|MPVE_↓_|MPVE_↓_|
|---|---|---|---|
|||H3.6M|SURREAL|
|(a)<br>(b)|Skeleton<br>Rand virtual marker|64.4<br>63.0|53.6<br>50.1|
|(c)|Virtual marker|**58.0**|**44.7**|



Table 4. Ablation study of the virtual marker representation for our approach on H3.6M and SURREAL datasets. “Skeleton” means the sparse landmark joint representation is used. “Rand virtual marker” means the virtual markers are randomly selected from all the vertices without learning. (c) is our method, where the learned virtual markers are used. 

method achieves a much lower MPVE than the baseline (a), demonstrating that the virtual markers help to estimate body shapes more accurately than the skeletons. In baseline (b), we randomly sample 64 from the 6890 mesh vertices as virtual markers. We repeat the experiment five times and report the average number. We can see that the result is worse than ours, which is because the randomly selected vertices may not be expressive to reconstruct the other vertices or can not 

539 

**==> picture [226 x 93] intentionally omitted <==**

**----- Start of picture text -----**<br>
als<br>Image  Pose2Mesh Ours GT<br>|<br>**----- End of picture text -----**<br>


|_K_|GT|GT|Det|Det|
|---|---|---|---|---|
||MPVE_↓_|MPJPE_↓_|MPVE_↓_|MPJPE_↓_|
|16<br>32<br>64<br>96|46.8<br>20.1<br>11.0<br>**9.9**|39.8<br>14.2<br>7.5<br>**5.6**|58.7<br>58.2<br>**58.0**<br>59.6|47.8<br>48.3<br>**47.3**<br>48.2|



Table 5. Ablation study of the different number of virtual markers ( _K_ ) on H3.6M [15] dataset. (GT) Mesh reconstruction results when GT 3D positions of the virtual markers are used in objective (1). (Det) Mesh estimation results obtained by our proposed framework when we use different numbers of virtual markers ( _K_ ). 

Figure 4. Mesh estimation results of different methods on H3.6M test set. Our method with virtual marker representation gets better shape estimation results than Pose2Mesh which uses skeleton representation. Note the waistline of the body and the thickness of the arm. 

**==> picture [201 x 13] intentionally omitted <==**

**----- Start of picture text -----**<br>
Input Image (a) Using fixed (b) Using updated<br>coefficient matrix coefficient matrix<br>**----- End of picture text -----**<br>


**==> picture [163 x 7] intentionally omitted <==**

**----- Start of picture text -----**<br>
(a) (b) (c)<br>**----- End of picture text -----**<br>


Figure 6. Mesh estimation comparison results when using (a) fixed coefficient matrix **A**[�] _[sym]_ , and (b) updated **A**[ˆ] . Please zoom in to better see the details. 

Figure 5. Visualization of the learned virtual markers of different numbers of _K_ = 16 _,_ 32 _,_ 96, from left to right, respectively. 

be accurately detected from images as they lack distinguishable visual patterns. The results validate the effectiveness of our learning strategy. 

Figure 1 shows some qualitative results on the SURREAL test set. The meshes estimated by the baseline which uses skeleton representation, _i.e_ . Pose2Mesh [7], have inaccurate body shapes. This is reasonable because the skeleton is oversimplified and has very limited capability to recover shapes. Instead, it implicitly learns a mean shape for the whole training dataset. In contrast, the mesh estimated by using virtual markers has much better quality due to its strong representation power and therefore can handle different body shapes elegantly. Figure 4 also shows some qualitative results on the H3.6M test set. For clarity, we draw the intermediate representation (blue balls) in it as well. 

**Number of virtual markers.** We evaluate how the number of virtual markers affects estimation quality on H3.6M [15] dataset. Figure 5 visualizes the learned virtual markers, which are all located on the body surface and close to the extreme points of the mesh. This is expected as mentioned in Section 3.1. Table 5 (GT) shows the mesh reconstruction results when we have GT 3D positions of the virtual markers in objective (1). When we increase the number of virtual markers, both mesh reconstruction error (MPVE) and the regressed landmark joint error (MPJPE) steadily decrease. This is expected because using more virtual markers improves the representation power. However, using more 

virtual markers cannot guarantee smaller estimation errors when we need to estimate the virtual marker positions from images as in our method. This is because the additional virtual markers may have large estimation errors which affect the mesh estimation result. The results are shown in Table 5 (Det). Increasing the number of virtual markers _K_ steadily reduces the MPVE errors when _K_ is smaller than 96. However, if we keep increasing _K_ , the error begins to increase. This is mainly because some of the newly introduced virtual markers are difficult to detect from images and therefore bring errors to mesh estimation. 

**Coefficient matrix.** We compare our method to a baseline which uses the fixed coefficient matrix **A**[�] _[sym]_ . We show the quality comparison in Figure 6. We can see that the estimated mesh by a fixed coefficient matrix (a) has mostly correct pose and shape but there are also some artifacts on the mesh while using the updated coefficient matrix (b) can get better mesh estimation results. As shown in Table 6, using a fixed coefficient matrix gets larger MPVE and MPJPE errors than using the updated coefficient matrix. This is caused by the estimation errors of virtual markers when occlusion happens, which is inevitable since the virtual markers on the back will be self-occluded by the front body. As a result, inaccurate marker positions would bring large errors to the final mesh estimates if we directly use the fixed matrix. 

## **4.5. Qualitative Results** 

Figure 7 (top) presents some meshes estimated by our approach on natural images from the 3DPW test set. The 

540 

**==> picture [50 x 8] intentionally omitted <==**

**----- Start of picture text -----**<br>
Failure case<br>**----- End of picture text -----**<br>


Figure 7. **Top:** Meshes estimated by our approach on images from 3DPW test set. The rightmost case in the dashed box shows a typical failure. **Bottom:** Meshes estimated by our approach on Internet images with challenging cases (extreme shapes or in a long dress). 

|No.<br>Method|Fixed �**A**_sym_<br>Updated ˆ**A**|MPVE_↓_<br>MPJPE_↓_|
|---|---|---|
|(a)<br>Ours (fixed)<br>(b)<br>Ours|✓<br>✗<br>✗<br>✓|64.7<br>51.6<br>**58.0**<br>**47.3**|



Table 6. Ablation study of the coefficient matrix for our approach on H3.6M dataset. **A** � _[sym]_ to reconstruct the mesh.“fixed” means using the fixed coefficient matrix 

**==> picture [113 x 9] intentionally omitted <==**

**----- Start of picture text -----**<br>
(a) a (b)<br>**----- End of picture text -----**<br>


rightmost case shows a typical failure where our method has a wrong pose estimate of the left leg due to heavy occlusion. We can see that the failure is constrained to the local region and the rest of the body still gets accurate estimates. We further analyze how inaccurate virtual markers would affect the mesh estimation, _i.e_ . when part of human body is occluded or truncated. According to the finally learned coefficient matrix **A[ˆ]** of our model, we highlight the relationship weights among virtual markers and all vertices in Figure 8. We can see that our model actually learns _local and sparse_ dependency between each vertex and the virtual markers, _e.g_ . for each vertex, the virtual markers that contribute the most are in a near range as shown in Figure 8 (b). Therefore, in inference, if a virtual marker has inaccurate position estimation due to occlusion or truncation, the dependent vertices may have inaccurate estimates, while the rest will be barely affected. Figure 2 (right) shows more examples where occlusion or truncation occurs, and our method can still get accurate or reasonable estimates robustly. Note that when truncation occurs, our method still guesses the positions of the truncated virtual markers. 

Figure 7 (bottom) shows our estimated meshes on challenging cases, which indicates the strong generalization ability of our model on diverse postures and actions in natural scenes. Please refer to the supplementary for more quality results. Note that since the datasets do not provide supervision of head orientation, face expression, hands, or feet, the estimates of these parts are just in canonical poses inevitably. 

Figure 8. (a) For each virtual marker (represented by a star), we highlight the top 30 most affected vertices (represented by a colored dot) based on average coefficient matrix **A[ˆ]** . (b) For each vertex (dot), we highlight the top 3 virtual markers (star) that contribute the most. We can see that the dependency has a strong locality which improves the robustness when some virtual markers cannot be accurately detected. 

Apart from that, most errors are due to inaccurate 3D virtual marker estimation which may be addressed using more powerful estimators or more diverse training datasets in the future. 

## **5. Conclusion** 

In this paper, we present a novel intermediate representation _Virtual Marker_ , which is more expressive than the prevailing skeleton representation and more accessible than physical markers. It can reconstruct 3D meshes more accurately and efficiently, especially in handling diverse body shapes. Besides, the coefficient matrix in the virtual marker representation encodes spatial relationships among mesh vertices which allows the method to implicitly explore structure priors of human body. It achieves better mesh estimation results than the state-of-the-art methods and shows advanced generalization potential in spite of its simplicity. 

## **Acknowledgement** 

This work was supported by MOST-2022ZD0114900 and NSFC-62061136001. 

541 

## **References** 

- [1] Anurag Arnab, Carl Doersch, and Andrew Zisserman. Exploiting temporal context for 3d human pose estimation in the wild. In _CVPR_ , pages 3395–3404, 2019. 

- [2] Federica Bogo, Angjoo Kanazawa, Christoph Lassner, Peter Gehler, Javier Romero, and Michael J Black. Keep it smpl: Automatic estimation of 3d human pose and shape from a single image. In _ECCV_ , pages 561–578, 2016. 

- [3] Ronan Boulic, Pascal Bécheiraz, Luc Emering, and Daniel Thalmann. Integration of motion control techniques for virtual human and avatar real-time animation. In _Proceedings of the ACM symposium on Virtual reality software and technology_ , pages 111–118, 1997. 

- [4] Yuansi Chen, Julien Mairal, and Zaid Harchaoui. Fast and robust archetypal analysis for representation learning. In _CVPR_ , pages 1478–1485, 2014. 

- [5] Junhyeong Cho, Kim Youwang, and Tae-Hyun Oh. Crossattention of disentangled modalities for 3d human mesh recovery with transformers. In _ECCV_ , 2022. 

- [6] Hongsuk Choi, Gyeongsik Moon, Ju Yong Chang, and Kyoung Mu Lee. Beyond static features for temporally consistent 3d human pose and shape from a video. In _CVPR_ , pages 1964–1973, 2021. 

- [7] Hongsuk Choi, Gyeongsik Moon, and Kyoung Mu Lee. Pose2mesh: Graph convolutional network for 3d human pose and mesh recovery from a 2d human pose. In _ECCV_ , pages 769–787, 2020. 

- [8] Hongsuk Choi, Gyeongsik Moon, JoonKyu Park, and Kyoung Mu Lee. Learning to estimate robust 3d human mesh from in-the-wild crowded scenes. In _CVPR_ , pages 1475–1484, June 2022. 

- [9] Vasileios Choutas, Georgios Pavlakos, Timo Bolkart, Dimitrios Tzionas, and Michael J Black. Monocular expressive body regression through body-driven attention. In _ECCV_ , pages 20–40, 2020. 

- [10] Hai Ci, Mingdong Wu, Wentao Zhu, Xiaoxuan Ma, Hao Dong, Fangwei Zhong, and Yizhou Wang. Gfpose: Learning 3d human pose prior with gradient fields. _arXiv preprint arXiv:2212.08641_ , 2022. 

- [11] Enric Corona, Gerard Pons-Moll, Guillem Alenyà, and Francesc Moreno-Noguer. Learned vertex descent: a new direction for 3d human model fitting. In _ECCV_ , pages 146– 165. Springer, 2022. 

- [12] Adele Cutler and Leo Breiman. Archetypal analysis. _Technometrics_ , 36(4):338–347, 1994. 

- [13] Shanyan Guan, Jingwei Xu, Michelle Z He, Yunbo Wang, Bingbing Ni, and Xiaokang Yang. Out-of-domain human mesh reconstruction via dynamic bilevel online adaptation. _IEEE TPAMI_ , 2022. 

- [14] Yinghao Huang, Federica Bogo, Christoph Lassner, Angjoo Kanazawa, Peter V Gehler, Javier Romero, Ijaz Akhter, and Michael J Black. Towards accurate marker-less human shape and pose estimation over time. In _3DV_ , pages 421–430, 2017. 

- [15] Catalin Ionescu, Dragos Papava, Vlad Olaru, and Cristian Sminchisescu. Human3. 6m: Large scale datasets and predictive methods for 3d human sensing in natural environments. _IEEE TPAMI_ , 36(7):1325–1339, 2013. 

- [16] Karim Iskakov, Egor Burkov, Victor Lempitsky, and Yury Malkov. Learnable triangulation of human pose. In _ICCV_ , pages 7718–7727, 2019. 

- [17] Ian T Jolliffe. Principal components in regression analysis. In _Principal component analysis_ , pages 129–155. Springer, 1986. 

- [18] Angjoo Kanazawa, Michael J Black, David W Jacobs, and Jitendra Malik. End-to-end recovery of human shape and pose. In _CVPR_ , pages 7122–7131, 2018. 

- [19] Angjoo Kanazawa, Jason Y Zhang, Panna Felsen, and Jitendra Malik. Learning 3d human dynamics from video. In _CVPR_ , pages 5614–5623, 2019. 

- [20] Rawal Khirodkar, Shashank Tripathi, and Kris Kitani. Occluded human mesh recovery. In _CVPR_ , pages 1715–1725, June 2022. 

- [21] Diederik P Kingma and Jimmy Ba. Adam: A method for stochastic optimization. In _ICLR_ , 2015. 

- [22] Muhammed Kocabas, Nikos Athanasiou, and Michael J Black. Vibe: Video inference for human body pose and shape estimation. In _CVPR_ , pages 5253–5263, 2020. 

- [23] Muhammed Kocabas, Chun-Hao P. Huang, Otmar Hilliges, and Michael J. Black. Pare: Part attention regressor for 3d human body estimation. In _ICCV_ , pages 11127–11137, October 2021. 

- [24] Nikos Kolotouros, Georgios Pavlakos, Michael J Black, and Kostas Daniilidis. Learning to reconstruct 3d human pose and shape via model-fitting in the loop. In _ICCV_ , pages 2252–2261, 2019. 

- [25] Nikos Kolotouros, Georgios Pavlakos, and Kostas Daniilidis. Convolutional mesh regression for single-image human shape reconstruction. In _CVPR_ , pages 4501–4510, 2019. 

- [26] Nikos Kolotouros, Georgios Pavlakos, Dinesh Jayaraman, and Kostas Daniilidis. Probabilistic modeling for human mesh recovery. In _ICCV_ , pages 11605–11614, October 2021. 

- [27] Christoph Lassner, Javier Romero, Martin Kiefel, Federica Bogo, Michael J Black, and Peter V Gehler. Unite the people: Closing the loop between 3d and 2d human representations. In _CVPR_ , pages 6050–6059, 2017. 

- [28] Jiefeng Li, Chao Xu, Zhicun Chen, Siyuan Bian, Lixin Yang, and Cewu Lu. Hybrik: A hybrid analytical-neural inverse kinematics solution for 3d human pose and shape estimation. In _CVPR_ , pages 3383–3393, 2021. 

- [29] Yong-Lu Li, Liang Xu, Xinpeng Liu, Xijie Huang, Yue Xu, Shiyi Wang, Hao-Shu Fang, Ze Ma, Mingyang Chen, and Cewu Lu. Pastanet: Toward human activity knowledge engine. In _CVPR_ , pages 382–391, 2020. 

- [30] Zhihao Li, Jianzhuang Liu, Zhensong Zhang, Songcen Xu, and Youliang Yan. Cliff: Carrying location information in full frames into human pose and shape estimation. In _ECCV_ , 2022. 

- [31] Kevin Lin, Lijuan Wang, and Zicheng Liu. End-to-end human pose and mesh reconstruction with transformers. In _CVPR_ , pages 1954–1963, 2021. 

- [32] Kevin Lin, Lijuan Wang, and Zicheng Liu. Mesh graphormer. In _ICCV_ , pages 12939–12948, 2021. 

- [33] Tsung-Yi Lin, Michael Maire, Serge Belongie, James Hays, Pietro Perona, Deva Ramanan, Piotr Dollár, and C Lawrence 

542 

   - Zitnick. Microsoft coco: Common objects in context. In _ECCV_ , pages 740–755, 2014. 

- [34] Matthew Loper, Naureen Mahmood, and Michael J Black. Mosh: Motion and shape capture from sparse markers. _TOG_ , 33(6):1–13, 2014. 

- [35] Matthew Loper, Naureen Mahmood, Javier Romero, Gerard Pons-Moll, and Michael J Black. Smpl: A skinned multiperson linear model. _TOG_ , 34(6):1–16, 2015. 

- [36] Tianyu Luan, Yali Wang, Junhao Zhang, Zhe Wang, Zhipeng Zhou, and Yu Qiao. Pc-hmr: Pose calibration for 3d human mesh recovery from 2d images/videos. In _AAAI_ , pages 2269– 2276, 2021. 

- [37] Dushyant Mehta, Helge Rhodin, Dan Casas, Pascal Fua, Oleksandr Sotnychenko, Weipeng Xu, and Christian Theobalt. Monocular 3d human pose estimation in the wild using improved cnn supervision. In _3DV_ , pages 506–516, 2017. 

- [38] Gyeongsik Moon and Kyoung Mu Lee. I2l-meshnet: Imageto-lixel prediction network for accurate 3d human pose and mesh estimation from a single rgb image. In _ECCV_ , pages 752–768, 2020. 

- [39] Mohamed Omran, Christoph Lassner, Gerard Pons-Moll, Peter Gehler, and Bernt Schiele. Neural body fitting: Unifying deep learning and model based human pose and shape estimation. In _3DV_ , pages 484–494. IEEE, 2018. 

- [40] Georgios Pavlakos, Vasileios Choutas, Nima Ghorbani, Timo Bolkart, Ahmed AA Osman, Dimitrios Tzionas, and Michael J Black. Expressive body capture: 3d hands, face, and body from a single image. In _CVPR_ , pages 10975–10985, 2019. 

- [41] Liliana Lo Presti and Marco La Cascia. 3d skeleton-based human action classification: A survey. _Pattern Recognition_ , 53:130–147, 2016. 

- [42] Haibo Qiu, Chunyu Wang, Jingdong Wang, Naiyan Wang, and Wenjun Zeng. Cross view fusion for 3d human pose estimation. In _ICCV_ , pages 4342–4351, 2019. 

- [43] Jiajun Su, Chunyu Wang, Xiaoxuan Ma, Wenjun Zeng, and Yizhou Wang. Virtualpose: Learning generalizable 3d human pose models from virtual data. In _ECCV_ , pages 55–71. Springer, 2022. 

- [44] Ke Sun, Bin Xiao, Dong Liu, and Jingdong Wang. Deep highresolution representation learning for human pose estimation. In _CVPR_ , pages 5693–5703, 2019. 

- [45] Xiao Sun, Bin Xiao, Fangyin Wei, Shuang Liang, and Yichen Wei. Integral human pose regression. In _ECCV_ , pages 529– 545, 2018. 

- [46] Yu Sun, Qian Bao, Wu Liu, Yili Fu, Michael J Black, and Tao Mei. Monocular, one-stage, regression of multiple 3d people. In _ICCV_ , pages 11179–11188, 2021. 

- [47] Yu Sun, Yun Ye, Wu Liu, Wenpeng Gao, Yili Fu, and Tao Mei. Human mesh recovery from monocular images via a skeleton-disentangled representation. In _ICCV_ , pages 5349– 5358, 2019. 

   - [50] Gul Varol, Duygu Ceylan, Bryan Russell, Jimei Yang, Ersin Yumer, Ivan Laptev, and Cordelia Schmid. Bodynet: Volumetric inference of 3d human body shapes. In _ECCV_ , pages 20–36, 2018. 

   - [51] Gul Varol, Javier Romero, Xavier Martin, Naureen Mahmood, Michael J Black, Ivan Laptev, and Cordelia Schmid. Learning from synthetic humans. In _CVPR_ , pages 109–117, 2017. 

   - [52] Timo von Marcard, Roberto Henschel, Michael J Black, Bodo Rosenhahn, and Gerard Pons-Moll. Recovering accurate 3d human pose in the wild using imus and a moving camera. In _ECCV_ , pages 601–617, 2018. 

   - [53] Ziniu Wan, Zhengjia Li, Maoqing Tian, Jianbo Liu, Shuai Yi, and Hongsheng Li. Encoder-decoder with multi-level attention for 3d human shape and pose estimation. In _ICCV_ , pages 13033–13042, 2021. 

   - [54] Nanyang Wang, Yinda Zhang, Zhuwen Li, Yanwei Fu, Wei Liu, and Yu-Gang Jiang. Pixel2mesh: Generating 3d mesh models from single rgb images. In _ECCV_ , pages 52–67, 2018. 

   - [55] Yuanlu Xu, Song-Chun Zhu, and Tony Tung. Denserac: Joint 3d pose and shape estimation by dense render-and-compare. In _ICCV_ , pages 7760–7770, 2019. 

   - [56] Chun-Han Yao, Jimei Yang, Duygu Ceylan, Yi Zhou, Yang Zhou, and Ming-Hsuan Yang. Learning visibility for robust dense human body estimation. In _ECCV_ , 2022. 

   - [57] Hang Ye, Wentao Zhu, Chunyu Wang, Rujie Wu, and Yizhou Wang. Faster voxelpose: Real-time 3d human pose estimation by orthographic projection. In _ECCV_ , pages 142–159. Springer, 2022. 

   - [58] Andrei Zanfir, Elisabeta Marinoiu, and Cristian Sminchisescu. Monocular 3d pose and shape estimation of multiple people in natural scenes-the importance of multiple scene constraints. In _CVPR_ , pages 2148–2157, 2018. 

   - [59] Mihai Zanfir, Andrei Zanfir, Eduard Gabriel Bazavan, William T Freeman, Rahul Sukthankar, and Cristian Sminchisescu. Thundr: Transformer-based 3d human reconstruction with markers. In _ICCV_ , pages 12971–12980, 2021. 

   - [60] Wang Zeng, Wanli Ouyang, Ping Luo, Wentao Liu, and Xiaogang Wang. 3d human mesh regression with dense correspondence. In _CVPR_ , pages 7054–7063, 2020. 

   - [61] Hongwen Zhang, Jie Cao, Guo Lu, Wanli Ouyang, and Zhenan Sun. Learning 3d human shape and pose from dense body parts. _IEEE TPAMI_ , 44(5):2610–2627, 2022. 

   - [62] Hongwen Zhang, Yating Tian, Xinchi Zhou, Wanli Ouyang, Yebin Liu, Limin Wang, and Zhenan Sun. Pymaf: 3d human pose and shape regression with pyramidal mesh alignment feedback loop. In _ICCV_ , pages 11446–11456, 2021. 

   - [63] Yifu Zhang, Chunyu Wang, Xinggang Wang, Wenyu Liu, and Wenjun Zeng. Voxeltrack: Multi-person 3d human pose estimation and tracking in the wild. _IEEE TPAMI_ , 45(2):2613– 2626, 2022. 

- [48] Hanyue Tu, Chunyu Wang, and Wenjun Zeng. Voxelpose: Towards multi-camera 3d human pose estimation in wild environment. In _ECCV_ , pages 197–212. Springer, 2020. 

- [49] Hsiao-Yu Tung, Hsiao-Wei Tung, Ersin Yumer, and Katerina Fragkiadaki. Self-supervised learning of motion capture. In _NIPS_ , volume 30, 2017. 

543 

