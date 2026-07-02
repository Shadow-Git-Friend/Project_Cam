This CVPR paper is the Open Access version, provided by the Computer Vision Foundation. Except for this watermark, it is identical to the accepted version; the final published version of the proceedings is available on IEEE Xplore. 

## **SIFU: Side-view Conditioned Implicit Function for Real-world Usable Clothed Human Reconstruction** 

Zechuan Zhang Zongxin Yang[†] Yi Yang ReLER, CCAI, Zhejiang University _{_ zechuan, yangzongxin, yangyics _}_ @zju.edu.cn 

**==> picture [490 x 169] intentionally omitted <==**

**----- Start of picture text -----**<br>
“Van Gogh Style”<br>Building Scenes with SIFU<br>zote ' y Reconstructed  i | i$ Bis<br>Humans<br>4<br>7<br>6<br>| a Mesh HL Texture Edited a 8. i f 7 . : ) aoe On lila i)<br>Input Image Diffusion Enhanced Texturing & Editing 4<br>3<br>/ | L Realistic Mie B e n tee te bus A<br>Texture<br>5 6<br>ae JF ae De i | } J ‘t | rr<br>2<br>1 A | eR See ee<br>1 2 3 1 5<br>Extreme Loose Challenging<br>Mesh Reconstructed by SIFU High Accuracy for 3D Printing Clothing Pose<br>**----- End of picture text -----**<br>


Figure 1. With just a single image, SIFU is capable of reconstructing a high-quality 3D clothed human model, making it well-suited for practical applications such as 3D printing and scene creation. At the heart of SIFU is a novel **Side-view Conditioned Implicit Function** , which is key to enhancing feature extraction and geometric precision. Furthermore, SIFU introduces a **3D Consistent Texture Refinement** process, greatly improving texture quality and facilitating texture editing with the help of text-to-image diffusion models. Notably proficient in dealing with complex poses and loose clothing, SIFU stands out as an ideal solution for real-world applications. 

## **Abstract** 

_Creating high-quality 3D models of clothed humans from single images for real-world applications is crucial. Despite recent advancements, accurately reconstructing humans in complex poses or with loose clothing from inthe-wild images, along with predicting textures for unseen areas, remains a significant challenge. A key limitation of previous methods is their insufficient prior guidance in transitioning from 2D to 3D and in texture prediction. In response, we introduce_ _**SIFU** (_ _**S** ide-view Conditioned_ _**I** mplicit_ _**F** unction for Real-world_ _**U** sable Clothed Human Reconstruction), a novel approach combining a Side-view Decoupling Transformer with a 3D Consistent Texture Refinement pipeline. SIFU employs a cross-attention mechanism within the transformer, using SMPL-X normals as queries to effectively decouple side-view features in the pro-_ 

> †Zongxin Yang is the corresponding author. 

_cess of mapping 2D features to 3D. This method not only improves the precision of the 3D models but also their robustness, especially when SMPL-X estimates are not perfect. Our texture refinement process leverages text-to-image diffusion-based prior to generate realistic and consistent textures for invisible views. Through extensive experiments, SIFU surpasses SOTA methods in both geometry and texture reconstruction, showcasing enhanced robustness in complex scenarios and achieving an unprecedented Chamfer and P2S measurement. Our approach extends to practical applications such as 3D printing and scene building, demonstrating its broad utility in real-world scenarios._ 

## **1. Introduction** 

High-quality 3D models of clothed humans are crucial in diverse sectors, including augmented and virtual reality (AR/VR), 3D printing, scene assembly, and filmmaking. The traditional process of creating these models not only 

9936 

**==> picture [231 x 69] intentionally omitted <==**

**----- Start of picture text -----**<br>
(a) Image FeaturesExtracting 2D (b) Features to 3DTranslating 2D (c) 3D Features forReconstruction<br>(a) (b) (c) (a) (b) (c) TexturePrior<br>Geometry Geometry Geometry Geometry Geometry<br>Prior Prior Prior Prior Prior<br>**----- End of picture text -----**<br>


Figure 2. **Contrast between previous methods (Left) and ours (Right):** Our approach improves the reconstruction process by incorporating additional guidance on geometry and texture priors. 

requires a considerable amount of time but also specialized equipment capable of capturing multi-view photographs, in addition to the reliance on skilled artists. Contrasting this, in everyday situations, we most often have access to monocular images of individuals, easily obtained through phone cameras or found on various web pages. Thus, a method that accurately reconstructs 3D human models from a single image could significantly cut costs and simplify the process of independent creation. While existing deep learning models [6, 11, 30, 69, 70, 81, 82, 85, 92, 93] show promise in this area, they struggle with complex poses and loose clothing, as illustrated in Fig. 3. Furthermore, these models fail to correctly texture hidden areas, resulting in less realistic outcomes. Therefore, there’s a significant need for models that can generalize across various scenarios and efficiently produce realistic, real-world applicable 3D clothed humans. 

Through analyzing existing methods, we pinpointed two key challenges in this field: **(i) Insufficient Prior Guidance in Translating 2D Features to 3D:** The reconstruction of 3D objects from 2D images typically involves three main steps: (a) _extracting 2D image features_ , (b) _translating 2D features to 3D_ , and (c) _3D features for reconstruction_ . As shown by Fig. 2, current approaches often add geometric prior (like SMPL-X [61]) to the first and last steps, focusing on techniques such as normal map prediction [81, 82, 85], SMPL-guided SDF [81, 85, 92], or volume features [10, 93]. While the use of priors for improving the transition from 2D image features to 3D is crucial, it remains underexplored. Currently, this transition is typically achieved by projecting features onto 3D points [6, 10, 11, 69, 70, 81, 85, 93] or by employing fixed learnable embeddings to generate 3D features [92]. These methods, however, do not fully harness the potential of priors in enhancing accuracy of 3D reconstruction. **(ii) Lack of Texture Prior:** While current methods [6, 11, 69, 70, 92] attempt to predict vertex colors, they struggle to accurately predict textures for unseen views, particularly with limited training data. This limitation highlights a need for additional texture priors in 3D human reconstruction. 

In response to the challenges we’ve identified, we propose two refined strategies to enhance 3D human reconstruction. **Firstly** , we believe that enhancing the process of translating 2D features to 3D with additional guid- 

**==> picture [151 x 201] intentionally omitted <==**

**----- Start of picture text -----**<br>
PIFu PaMIR SIFU<br>a the AI A<br>Sy Y . ty \C<br>ICON ECON SIFU<br>a os"<br>i Qs ;<br>D-IF GTA SIFU<br>PIFu PIFuHD SIFU<br>**----- End of picture text -----**<br>


Figure 3. **Comparison of SIFU with State-of-the-Art (SOTA) Methods in 3D Human Inference from In-the-Wild Images.** Existing SOTA methods often struggle with complex poses and loose clothing, leading to a range of artifacts. These issues include the absence of human shapes (PIFu, PaMIR, PIFuHD), missing body parts (ECON), disrupted clothing (ICON, D-IF), and a lack of fine details (GTA). In contrast, SIFU effectively addresses these challenges, delivering high-quality, detailed results. 

ance could significantly improve both the accuracy and efficiency of 3D reconstructions. To more effectively integrate prior guidance, such as SMPL-X [61], with image features, we utilize the cross-attention mechanism of the transformer [77]. This approach aims to optimize the fusion of geometry and image data, potentially leading to more precise and realistic 3D human models. **Secondly** , considering the impressive generative capabilities of pretrained diffusion models, as shown in recent studies [12, 13, 25, 57, 73] and their proficiency in learning rich 3D priors [48–51, 64, 65, 76], we suggest their incorporation as priors to enhance texture prediction, particularly for invisible regions. Besides, maintaining 3D consistency from different angles and matching the style of the input image is also crucial for creating realistic textures. 

In this paper, we present **SIFU** ( **S** ide-view Conditioned **I** mplicit **F** unction for Real-world **U** sable Clothed Human Reconstruction), a novel approach employing a **Side-view Conditioned Implicit Function (§3.2)** with a **3D Consistent Texture Refinement (§3.3)** pipeline for precise geometry and realistic texture reconstruction. Our approach employs normals from SMPL-X as queries in a cross-attention mechanism with image features. This method effectively 

9937 

decouples side-view features in the process of mapping 2D features to 3D, thereby enhancing the accuracy and robustness of reconstruction. Moreover, our texture refinement employs text-to-image diffusion models [68] and ensures uniform diffusion features across different perspectives, resulting in detailed, consistently styled textures. 

Through extensive experiments, **SIFU** outperforms existing SOTA methods in geometry and texture quality, achieving an unprecedented Chamfer and P2S measurement of **0.6 cm** on THuman2.0 [87] (Tab. 1). Additionally, SIFU shows improved robustness in geometry reconstruction (Tab. 2), even with inaccurate SMPL-X estimations. SIFU handles complex poses and loose clothing well, producing realistic textures with consistent colors and patterns (Fig. 7). Its adaptability extends to practical applications like 3D printing and scene creation (Fig. 1), showcasing its broad practical utility. Key contributions include: 

- A novel **Side-view Conditioned Implicit Function** that skillfully maps 2D image features to 3D with SMPL-X guidance. This is the first instance showcasing the efficacy of using human prior information to decouple sideview 3D features from the input image, significantly advancing the field of clothed human reconstruction. 

- A **3D Consistent Texture Refinement** pipeline designed to generate realistic, 3D consistent textures on clothed human meshes. This approach has notably improved the quality and uniformity of textures, offering a substantial advancement in the field. 

- Our proposed model achieves state-of-the-art performance in both geometry and texture reconstruction, facilitating **real-world applications** such as 3D printing and scene building, which were challenging to achieve with previous methods. 

## **2. Related Work** 

**Implicit-function-based Reconstruction.** Implicit representations, such as occupancy and signed distance fields, are flexible with topology and can effectively depict 3D clothed humans across a variety of scenarios, including loose garments and complex poses. A series of studies have focused on regressing the implicit surface from a single input image directly in a streamlined process [1, 6, 21, 69, 70]. Others incorporate a 3D human body prior to enhance the process of 2D feature extraction and 3D feature for reconstruction [9–11, 23, 24, 29, 31, 47, 81, 82, 85, 92, 93]. Among these, GTA [92] utilizes transformers with fixed learnable embeddings to translating image features to 3D tri-plane features. As for texture reconstruction, methods like PIFu [69], ARCH [24, 31], PaMIR [93], and GTA [92] deduce full textures from a single image. Techniques such as PHORHUM [6] and S3F [11] go further by segregating albedo and global illumination. Nevertheless, these methods lack information from other views or prior knowledge 

(such as diffusion models), resulting in unsatisfactory textures. HumanSGD [1] employs diffusion models for mesh inpainting but faces performance declines with mesh reconstruction inaccuracies. TeCH [29] uses diffusion-based models for visualizing unseen areas, yielding realistic results. Its limitations, however, include time-intensive persubject optimization and dependence on accurate SMPL-X. **Explicit-shape-based Reconstruction.** Recovering the human mesh from a single RGB image is a complex challenge that has received extensive attention. Many approaches [15, 16, 37–41, 43, 44, 46, 90, 91] adopt parametric body models [36, 52, 60, 83] to estimate the shape and pose of a 3D human body with minimal clothing [45, 71]. To incorporate clothing into the 3D models, methods often apply 3D clothing offsets [2–5, 42, 80, 94] or use adjustable garment templates [8, 16, 32] over the base body shape. Additionally, non-parametric forms like depth maps [17, 72], normal maps [82], and point clouds [89] are explored for creating representations of clothed humans. 

Despite these advancements, explicit-shape approaches can be limited by topological constraints, which become apparent when handling diverse and complex clothing styles found in real-world settings, such as dresses, and skirts. **NeRF-based Reconstruction.** The rise of Neural Radiance Fields (NeRF) has seen methods [18, 20, 33, 34, 56, 59, 62, 63, 78, 88] using videos or multi-view images to optimize NeRF for human form capture. Recent advancements like SHERF [26] and ELICIT [28] aim to generate human NeRFs from single images, with SHERF filling gaps using 2D image data and ELICIT employing a pre-trained CLIP model [66] for contextual understanding. While NeRFbased approaches are effective in creating quality images from various perspectives, they typically struggle with detailed 3D mesh generation from single images and often require extensive time for optimization. 

Contrasting with these methods, SIFU stands out in reconstructing clothed human meshes across various scenarios, producing consistently realistic 3D textures suitable for real-world use. It leverages human body priors to decouple side-view features from input images during the 2D to 3D mapping process, thereby improving the accuracy of its implicit function. For texture refinement, SIFU adopts a coarse-to-fine approach, utilizing a pre-trained diffusion model, trained on a vast dataset, to predict textures in unseen areas. It also reconstructs texture from the input image for visible regions, ensuring uniform texture consistency. 

## **3. Method** 

Given a single image, SIFU first reconstructs the 3D mesh and coarse textures using the Side-view Conditioned Implicit Function (Sec. 3.2). Subsequently, it employs a 3D Consistent Texture Refinement process (Sec. 3.3) to enhance textures, ensuring high quality and 3D consistency. 

9938 

**==> picture [474 x 304] intentionally omitted <==**

**----- Start of picture text -----**<br>
Side-view Decoupling  Front Hybrid Prior Fusion<br>Transformer q Stragegy<br>k Front<br>Right<br>v<br>Front-decoder Mesh<br>Back<br>Right<br>v LeftBack Left MLP<br>Image Global-encoder v<br>k Front<br>Right-view k Right<br>o :  g concat operation Itt ; Left-viewBack-view q qSide-decoders | LeftBack Gp query point : W~< Coarse<br>: normal feature<br>Texture<br>   and SDF ee SMPL-X Side-views 4<br>the back side of a man in a  3D Consistent<br>light blue and white striped<br>Texture Refinement<br>shirt who is celebrating a<br>goal with his arms in ...... ...<br>Stable Diffusion<br>L ~\ Oo i fr “iy ¥<br>Image-to-Text PP — : oA TY To" fa Coarse Textured Mesh at<br>Rendering<br>Invisible Region<br>Loss<br>Optimize<br>Consistent Edited Views Mapping<br>Optimize<br>MSE( , )<br>Refined Texture<br>Image Render Input View UV Map<br>Mapping<br>**----- End of picture text -----**<br>


Figure 4. Given a single image, SIFU constructs a 3D clothed human mesh with coarse textures using a **Side-view Conditioned Implicit Function** (§3.2). This is followed by a step of **3D Consistent Texture Refinement** (§3.3) to generate detailed textures. Specifically, SIFU employs a side-view decoupling transformer to decouple features from the input image and the side-view normals of the SMPL-X model. Then, these features are combined at a query point through a hybrid prior fusion strategy, aiding in the reconstruction of both the mesh and its texture. Finally, the mesh with its basic textures undergoes a diffusion-based 3D consistent texture refinement, ensuring feature consistency in the latent space and resulting in high-quality textures. 

Key preliminary concepts necessary for understanding our approach are briefly presented in Sec. 3.1. 

## **3.1. Preliminary** 

**Implicit Function** is a powerful tool for modeling complex geometries and colors with neural networks. We employ implicit function to predict an occupancy field to represent 3D clothed humans. Specifically, our implicit function _IF_ maps an input point _**x**_ to a scalar value representing the spatial field including occupancy and color fields. Our reconstructed human surface can be represented as _SIF_ : 

**==> picture [192 x 12] intentionally omitted <==**

where occupancy _**o**_ = 0.5 and color _**c** ∈_ R[3] . **SMPL and SMPL-X.** The Skinned Multi-Person Linear (SMPL) model [52] is a parametric model for human body representation. It uses shape parameters _**β** ∈_ R[10] and pose parameters _**θ** ∈_ R[3] _[×]_[24] to define the human body mesh _M_ : 

**==> picture [179 x 12] intentionally omitted <==**

Here, _**β**_ controls body size, while _**θ**_ affects joint positions and orientations. The SMPL-X model [61] builds upon SMPL, adding features for hands and face, enhancing facial expressions, finger movements, and detailed body poses. **Diffusion Models.** Diffusion processes, notably represented by Diffusion Probabilistic Models (DPM) [12, 13, 25, 57, 73], are pivotal in image generation and have shown capabilities in human/avatar generation [27, 84]. These models aim to approximate a data distribution _q_ through a progressive denoising process. Starting with a Gaussian i.i.d noisy image _**x** T ∼N_ (0 _, I_ ), the model denoises it until a clean image _**x**_ 0 from the target distribution _q_ is obtained. DPMs can also learn a conditional distribution with additional guiding signals like text conditioning. 

## **3.2. Side-view Conditioned Implicit Function** 

The Side-view Conditioned Implicit Function in our model comprises two key components: the **Side-view Decoupling Transformer** and the **Hybrid Prior Fusion Strategy** . The transformer initially uses rendered SMPL-X images from 

9939 

various side views as queries to perform cross-attention with the encoded input image. This process effectively decouples features conditioned on the side views. The Hybrid Prior Fusion Strategy then integrates these features at each query point, which are later input into a Multi-Layer Perceptron (MLP) for predicting occupancy and color. We detail both components in the sections below. 

**Side-view Decoupling Transformer.** Our method draws inspiration from the shared characteristics, such as material and color, between side views (like the back or left side) and the visible front view. Despite their different perspectives, these similarities in features are crucial. Therefore, we aim to effectively separate side-view features from the front view, utilizing the SMPL-X model [61] as a guide. 

The process begins with a ViT-based global encoder [14], which encodes the input image _I_ into a latent feature _h_ , capturing the image’s globally correlated features. To decode these features, we employ two decoders: a front-view decoder, aligned with _h_ , and a side-view decoder. The front-view decoder utilizes multi-head selfattention within a vision transformer to process the front view feature, represented as _Ffront ∈_ R _[H][×][W][ ×][C]_ . 

To decouple side-view features, we render the sideview normal images _Ni_ of SMPL-X as guidance, with _i ∈{left, back, right}_ during the experiments. The sideview normals _Ni_ are transformed to embeddings _zi_ , which then engage in a cross-attention operation as queries, with the latent feature _h_ acting as both keys and values: 

**==> picture [231 x 23] intentionally omitted <==**

where **SM** represents **SoftMax** operation, while _W[Q]_ , _W[K]_ , and _W[V]_ are learnable parameters and _d_ is the scaling coefficient. Following the original transformer architecture [77], our model integrates residual connections [22] and layer normalization [7] after each sub-layer. The entire side-decoder contains multiple identical layers, and we deploy three such decoders to yield feature maps _Fi ∈_ R _[H][×][W][ ×][C]_ where _i ∈{left, back, right}_ . 

**Hybrid Prior Fusion Strategy.** In our pipeline, we incorporate the Hybrid Prior Fusion Strategy from [92] to effectively merge features at a query point, utilizing both spatial localization and human body prior knowledge. We split the feature maps _Fj_ (for _j ∈{front, left, back, right}_ ) into two groups. For the spatial query group, we project query points onto the feature map to obtain pixel-aligned features _Fj[S]_[.][We then combine these features from all planes using] a mix of averaging and concatenation: 

**==> picture [224 x 14] intentionally omitted <==**

where _f, l, b, r_ denote the front, left, back, and right respectively. For the other group, similar to the spatial query, we project the SMPL-X [61] mesh vertices onto the four 

feature maps, obtaining the feature _F[S]_ ( _**v**_ ), _**v** ∈M_ , where _M_ is the SMPL-X mesh. For each query point _**x**_ , we find its nearest triangular face _t_ _**x**_ = [ _**v**_ 0 _,_ _**v**_ 1 _,_ _**v**_ 2] _∈_ R[3] _[×]_[3] and employ barycentric interpolation to integrate features for _**x**_ , denoted as _F[P]_ ( _**x**_ ): 

**==> picture [209 x 12] intentionally omitted <==**

where [ _u, v, w_ ] represents the barycentric coordinates of the query point _**x**_ projected onto triangle _t_ _**x**_ . We concatenate these two query features as the final point feature. Moreover, we incorporate the signed distance between the query point and SMPL-X mesh _SDF_ ( _**x**_ ) and pixel-aligned normal feature _F[N]_ ( _**x**_ ) as input to a Multilayer Perceptron (MLP) for prediction of occupancy and color: 

**==> picture [215 x 11] intentionally omitted <==**

**Training Objectives.** We consider two sets of points as training data, denoted as _Go_ and _Gc_ . _Gc_ is sampled uniformly with a slight perturbation along the normals of the ground-truth mesh surface, whereas _Go_ is sampled according to the same strategy as in [69]. For the points in _Go_ , we employ the following loss function: 

**==> picture [182 x 24] intentionally omitted <==**

where _o_ ˆ _**x**_ denotes the model’s predicted occupancy, while _o_ _**x**_ is the ground-truth occupancy. For the sampled points in _Gc_ , we apply the following loss function: 

**==> picture [169 x 25] intentionally omitted <==**

where **ˆ** _**cx**_ denotes the predicted color, and _**cx**_ represents the corresponding ground-truth color. The total loss is the sum of these two separate losses, which is designed to fulfill a comprehensive training objective. 

**Mesh Extraction.** We begin by densely sampling points in space and using our side-view conditioned implicit function to predict their occupancy values. The Marching Cubes algorithm [53] is then applied to extract the mesh, and following [82], we substitute the hands with SMPL-X models for enhanced visuals. Finally, these mesh points are processed through the implicit function again for color prediction. 

## **3.3. 3D Consistent Texture Refinement** 

Upon extracting the mesh using our implicit function, we noted that color quality was coarse and areas not visible in the input were blurry, leading to a less realistic look (see Fig. 4). To address this, we developed a **3D Consistent Texture Refinement** pipeline, leveraging text-to-image diffusion priors to substantially enhance texture quality. **Pipeline.** For a given input image and its reconstructed mesh _M_ , we first utilize vision-to-text models ( _e.g_ ., [54, 58, 

9940 

||CAPE-NFP|CAPE-FP|THuman2.0|
|---|---|---|---|
|Method<br>Publication|Chamfer _↓_<br>P2S _↓_<br>Normal _↓_|Chamfer _↓_<br>P2S _↓_<br>Normal _↓_|Chamfer _↓_<br>P2S _↓_<br>Normal _↓_|
|_w/o SMPL-X body prior_||||
|PIFu * [69]<br>ICCV 2019<br>PIFuHD[70]<br>CVPR 2020|2.5609<br>1.9971<br>0.1023<br>3.7670<br>3.5910<br>0.1230|1.8139<br>1.5108<br>0.0798<br>2.3020<br>2.3350<br>0.0900|1.5991<br>1.4333<br>0.0843<br>-<br>-<br>-|
|_w/ SMPL-X body prior_||||
|PaMIR * [93]<br>TPAMI 2021<br>ICON [81]<br>CVPR 2022<br>ECON [82]<br>CVPR 2023<br>D-IF [85]<br>ICCV 2023<br>GTA[92]<br>NeurIPS 2023|1.6313<br>1.2666<br>0.0730<br>0.8846<br>0.8569<br>0.0434<br>0.9462<br>0.9334<br>0.0382<br>0.8237<br>0.8353<br>0.0575<br>0.8508<br>0.7920<br>0.0424|1.481<br>1.1631<br>0.0727<br>0.7247<br>0.6979<br>0.0371<br>0.9039<br>0.8938<br>0.0373<br>0.7625<br>0.769<br>0.0503|1.2152<br>1.0582<br>0.0730<br>0.9491<br>0.9846<br>0.0621<br>1.2585<br>1.4184<br>0.0612<br>1.1696<br>1.2900<br>0.0936|
|||0.6525<br>0.6084<br>0.0349|0.7329<br>0.7297<br>0.0492|
|**Ours**<br>-|**0.7725**<br>**0.7354**<br>**0.0378**|**0.6297**<br>**0.5980**<br>**0.0327**|**0.5961**<br>**0.6058**<br>**0.0407**|



Table 1. **Quantitative evaluation against SOTA (§4.1).** All models use a resolution of 256 for marching cubes and ground-truth SMPL-X models are used during testing. *Methods are re-implemented in [81] for a fair comparison. Top two results are colored as first second . 

86]) to convert the image into a textual description _P_ , and then back-project the mesh color onto a UV texture map _T_ , following the approach in [75]. To visualize unseen mesh areas, differentiable rendering _I_ is employed on mesh _M_ , generating images of these invisible views: 

**==> picture [152 x 11] intentionally omitted <==**

where _**k**_ = _{k_[1] _, ..., k[n] }_ represent camera views and _**I**_ = _{I_[1] _, ..., I[n] }_ are the corresponding rendered images. 

Subsequently, a pretrained and fixed text-to-image diffusion model _**ϵθ**_ refines the blurry images _**I**_ into enhanced images _**J**_ , using _P_ as a condition. To ensure consistency among refined images, a **consistent editing** technique _H_ is applied to _**ϵθ**_ , preserving the original semantic layout of _**I**_ : 

**==> picture [204 x 11] intentionally omitted <==**

where _**J**_ = _{J_[1] _, ..., J[n] }_ corresponds to the refined views of _**I**_ . After obtaining _**J**_ , a pixel-wise Mean Squared Error (MSE) loss is computed between each _J[i]_ and _I[i]_ to optimize the texture map _T_ . Additional losses include a perceptual loss _Lvgg_ [35] and a Chamfer Distance loss _LCD_ [29], aimed at ensuring style similarity between _J_ and the input image. We also compute an MSE loss _L[f] MSE_[from the in-] put view against the input image. These combined losses jointly optimize _T_ , enhancing overall texture quality: 

**==> picture [224 x 17] intentionally omitted <==**

where _λ_ 1 _, λ_ 2 _, λ_ 3 _, λ_ 4 are the weights attributed to each loss. **Consistent Editing.** To achieve consistent image editing across different views, we adopt a method inspired by [19]. This involves enforcing consistency among diffusion features from various rendered views. We perform DDIM inversion [74] on the input image _**I**_ , extracting diffusion tokens across all layers. A set of key views is selected for joint editing [79], ensuring a unified appearance in the resultant features. These features are then propagated to all views using a nearest-neighbor approach to maintain coherence across them. Please refer to the SupMat for more detailed procedural insights and specific mechanisms. 

|Method|Backbone|Chamfer _↓_<br>P2S _↓_<br>Normal _↓_|
|---|---|---|
|PaMIR [93]<br>ICON [81]<br>D-IF [85]<br>ECON [82]<br>GTA[92]|CNN<br>CNN<br>CNN<br>-<br>Transformer|1.3224<br>1.1349<br>0.0767<br>1.2935<br>1.3949<br>0.0781<br>1.5262<br>1.7296<br>0.1191<br>2.1195<br>1.8074<br>0.1029|
|||1.0473<br>1.0780<br>0.0649|
|**Ours**|Transformer|**0.9937**<br>**1.0645**<br>**0.0599**|



Table 2. **Assessing model robustness to SMPL-X (§4.1).** To evaluate the models’ robustness in reconstruction, we used the THuman2.0 dataset [87] and introduced random noise to the ground-truth SMPL-X models. This approach simulates inaccuracies in poses and shapes for robustness testing. 

## **4. Experiment** 

**Datasets.** We trained our model on the THuman2.0 dataset [87], comprising 526 human scans, with 490 used for training, 15 for validation, and 21 for testing. Groundtruth SMPL-X models were used during training, and PIXIE [15] was employed for inference. Our main evaluations were conducted on the CAPE [55] and THuman2.0 datasets. To test our model’s versatility with different poses, we divided the CAPE dataset into ”CAPE-FP” and ”CAPENFP” subsets. Further details on datasets and implementation are available in the SupMat. 

## **4.1. Evaluation** 

**Metrics.** Our model’s reconstruction quality for geometry is quantitatively evaluated using Chamfer and P2S distances, comparing reconstructed meshes with ground-truth. We also measure L2 Normal error between normal images from both meshes, assessing surface detail consistency by rotating the camera at _{_ 0 _[◦] ,_ 90 _[◦] ,_ 180 _[◦] ,_ 270 _[◦] }_ relative to the input view. For texture quality, we report the PSNR on colored images rendered similarly to normal images. 

**Quantitative Evaluation.** In geometry evaluation, our experiments utilize the ground-truth SMPL-X model for methods using a ”SMPL-X body prior,” as shown in Tab. 1. SIFU establishes a new standard in all metrics, especially excelling on the THuman2.0 dataset with an unprecedented Chamfer and P2S of **0.6 cm** . This highlights SIFU’s proficiency in accurate reconstructions across diverse scenarios, 

9941 

|(a) Quantitative comparison of texture quality on THuman2.0 [87].<br>22.10 <br> <br> <br>&<br>~~TO~~|Method<br>Chamfer _↓_<br>P2S _↓_<br>Normal _↓_<br>_A - Different Backbone_<br>no cross-attention<br>0.9846<br>0.8672<br>0.0477<br>learnable embedding<br>0.9860<br>0.8538<br>0.0471<br>use convolution network<br>0.8699<br>0.8221<br>0.0387<br>_B - Different Feature Plane_<br>only front plane<br>1.1165<br>0.9574<br>0.0558<br>front and back planes<br>0.9929<br>0.9189<br>0.0464<br>w/o left plane<br>0.7941<br>0.7576<br>0.0387<br>w/o rightplane<br>0.8058<br>0.7671<br>0.0386<br>_C - DifferentQuery Strategy_<br>pixel-aligned<br>0.8111<br>0.7615<br>0.0400<br>**Ours**<br>**0.7725**<br>**0.7354**<br>**0.0378**<br>Table3.**Ablationstudy(§4.2).**Wequantitativelyevaluatethe<br> ~~es~~<br> ~~a~~<br> ~~a~~<br>~~————~~|
|---|---|



**==> picture [216 x 213] intentionally omitted <==**

**----- Start of picture text -----**<br>
PSNR<br>18.09 18.05<br>(a) Quantitative comparison of texture quality on THuman2.0 [87].<br>PIFu ARCH ARCH++ PHORHUM S3F GTA<br>TO b a e h m e a &<br>aNR;aAK=AKq<br>Image PIFu GTA SIFU<br>(b) Qualitative results on Thuman2.0 [87]<br>**----- End of picture text -----**<br>


Table 3. **Ablation study (§4.2).** We quantitatively evaluate the contribution of each component in our model. The evaluation is performed on the CAPE-NFP dataset, with ground-truth SMPL-X models provided during the testing phase. 

Figure 5. **Texture comparison against SOTAs (§4.1).** We quantitatively and qualitatively compare texture quality on THuman2.0 [87]. PIXIE [15] used for SMPL-X estimation during testing. Please **zoom in** for details. " 

**==> picture [209 x 6] intentionally omitted <==**

**----- Start of picture text -----**<br>
Image TEXTure DreamGaussian SIFU(w/o refine) SIFU<br>**----- End of picture text -----**<br>


benefiting from our side-view conditioned approach. 

For texture reconstruction, SIFU surpasses PIFu [69] by **22.2%** in PSNR, demonstrating its superior texture quality. For visual comparisons, refer to Fig. 5 and the SupMat. **Robustness to SMPL-X.** In real-world scenarios, encountering in-the-wild images lacking precise SMPL-X parameters is common. The ability to handle SMPL-X estimation errors is crucial for high-quality reconstructions. We evaluated our model’s resilience by introducing noise (scaled by 0.05) to the pose and shape parameters of the ground-truth SMPL-X models. As shown in Tab. 2, SIFU demonstrates significant robustness, indicating strong practical utility. **Qualitative Results.** Our results showcase the model’s strong performance on in-the-wild images. As depicted in Fig. 7, our model is capable of handling complex scenarios such as loose clothing and challenging poses with proficiency. Further examples are provided in the SupMat. 

## **4.2. Ablation Studies** 

**Different Backbone Analysis.** In validating the effectiveness of our side-view decoupling transformer, we experimented with various alternative architectures. As per the results in Tab. 3, self-attention and learnable embeddings, without SMPL-X guidance, led to significant errors, and even convolutional networks with similar capacities were unable to effectively link input images with SMPL-X conditioned views. This ablation study clearly demonstrates that our custom transformer architecture excels, delivering superior reconstruction results. 

**Different Feature Plane Analysis.** In assessing the effect 

Figure 6. **Ablation on texture refinement (§4.2).** We compare our 3D consistent texture refinement with other diffusion-based methods on in-the-wild images. Please Q **zoom in** to see details. 

of various numbers of side-view feature planes, we found, as shown in Tab. 3, that adding just the left or right sideview planes most significantly improved accuracy, reducing the Chamfer by about 0.2 cm. The inclusion of all four planes offered a smaller error reduction, approximately 0.03 cm. Considering the minor improvements from more planes against the added complexity, we chose a balanced approach with four planes, as shown in Fig. 4. 

**Query Strategy Efficacy.** We compared the hybrid prior fusion strategy with the pixel-aligned method [69, 70, 81]. As shown in Tab. 3, the hybrid approach consistently outperforms the conventional method in all evaluation metrics. **Different Texture Refinement.** In comparing our approach with diffusion-based methods like TEXTure [67] and DreamGaussian [75] (using Zero123 XL [50]), and also against our model without refinement, it is evident from Fig. 6 that our 3D Consistent Texture Refinement method excels in both texture quality and consistency. 

## **4.3. Applications** 

**Texture Editing.** With the powerful ability of text-to-image diffusion models, we can change the text prompt to easily generate edited textures in the 3D consistent texture refinement. The edited results are shown in Fig. 1 and Fig. 8. **Scene Building and 3D Printing.** The model’s accurate ge- 

9942 

Figure 7. **Qualitative results on in-the-Wild images (§4.1):** The first two rows present results for humans wearing loose clothing, and the subsequent two rows display outcomes for humans in challenging poses. ( Q **Zoom in** for detailed view) 

**==> picture [220 x 6] intentionally omitted <==**

**----- Start of picture text -----**<br>
NBA Rockets NBA Lakers Iron Man Pencil Sketch Van Gogh<br>**----- End of picture text -----**<br>


Figure 8. **Texture editing (§4.3).** We edit the texture of the individual in Fig. 4 to achieve diverse outcomes by changing the text prompt in our 3D Consistent Texture Refinement. 

ometry and refined textures make it ideal for virtual scene creation and 3D printing (see Figs. 1 and 9 and SupMat). It enhances realism in simulations and games and streamlines the 3D printing process, reducing the need for complex scanning. This has potential applications in rapid prototyping, educational resources, and custom 3D figurines. 

## **5. Conclusion** 

We introduce SIFU, a novel method for reconstructing highquality 3D clothed human meshes, complete with detailed textures. Our method employs SMPL-X normals [61] as queries in a cross-attention mechanism with image features, efficiently decoupling side-view features during the conversion of 2D features to 3D. This process significantly improves geometric accuracy and robustness in our 3D reconstructions. Moreover, we design a 3D Consistent Texture 

Figure 9. **Building scenes with SIFU reconstructed humans (§4.3).** We showcase examples of building impressive scenes with SIFU reconstructed humans. Please Q **zoom in** to see details. 

Refinement process, which employs text-to-image diffusion priors while maintaining consistency among diffusion features in the latent space. This innovative approach ensures the creation of realistic textures, particularly in regions that are not visible in the initial input. SIFU distinctly outperforms existing methods in terms of both geometric and textural fidelity, showcasing exceptional capabilities in handling complex poses and loose clothing. These qualities make SIFU highly suitable for real-world applications. **Acknowledgements.** This work was supported by the National Natural Science Foundation of China (U2336212) and the Fundamental Research Funds for the Central Universities (No. 226-2022-00051). 

9943 

## **References** 

- [1] Badour AlBahar, Shunsuke Saito, Hung-Yu Tseng, Changil Kim, Johannes Kopf, and Jia-Bin Huang. Single-image 3d human digitization with shape-guided diffusion. In _SIGGRAPH Asia_ , 2023. 3 

- [2] Thiemo Alldieck, Marcus A. Magnor, Weipeng Xu, Christian Theobalt, and Gerard Pons-Moll. Detailed human avatars from monocular video. In _International Conference on 3D Vision (3DV)_ , 2018. 3 

- [3] Thiemo Alldieck, Marcus A. Magnor, Weipeng Xu, Christian Theobalt, and Gerard Pons-Moll. Video based reconstruction of 3D people models. In _CVPR_ , 2018. 

- [4] Thiemo Alldieck, Marcus A. Magnor, Bharat Lal Bhatnagar, Christian Theobalt, and Gerard Pons-Moll. Learning to reconstruct people in clothing from a single RGB camera. In _CVPR_ , 2019. 

- [5] Thiemo Alldieck, Gerard Pons-Moll, Christian Theobalt, and Marcus Magnor. Tex2Shape: Detailed Full Human Body Geometry From a Single Image. In _ICCV_ , 2019. 3 

- [6] Thiemo Alldieck, Mihai Zanfir, and Cristian Sminchisescu. Photorealistic monocular 3d reconstruction of humans wearing clothing. In _CVPR_ , 2022. 2, 3 

- [7] Jimmy Lei Ba, Jamie Ryan Kiros, and Geoffrey E Hinton. Layer normalization. _arXiv preprint arXiv:1607.06450_ , 2016. 5 

- [8] Bharat Lal Bhatnagar, Garvita Tiwari, Christian Theobalt, and Gerard Pons-Moll. Multi-Garment Net: Learning to dress 3D people from images. In _ICCV_ , 2019. 3 

- [9] Yukang Cao, Guanying Chen, Kai Han, Wenqi Yang, and Kwan-Yee K. Wong. JIFF: Jointly-aligned Implicit Face Function for High Quality Single View Clothed Human Reconstruction. In _CVPR_ , 2022. 3 

- [10] Yukang Cao, Kai Han, and Kwan-Yee K. Wong. Sesdf: Selfevolved signed distance field for implicit 3d clothed human reconstruction. In _IEEE Conference on Computer Vision and Pattern Recognition (CVPR)_ , 2023. 2 

- [11] Enric Corona, Mihai Zanfir, Thiemo Alldieck, Eduard Gabriel Bazavan, Andrei Zanfir, and Cristian Sminchisescu. Structured 3d features for reconstructing relightable and animatable avatars. In _CVPR_ , 2023. 2, 3 

- [12] Florinel-Alin Croitoru, Vlad Hondru, Radu Tudor Ionescu, and Mubarak Shah. Diffusion models in vision: A survey. _IEEE Transactions on Pattern Analysis and Machine Intelligence_ , 2023. 2, 4 

- [13] Prafulla Dhariwal and Alexander Nichol. Diffusion models beat gans on image synthesis. _Advances in neural information processing systems_ , 34:8780–8794, 2021. 2, 4 

- [14] Alexey Dosovitskiy, Lucas Beyer, Alexander Kolesnikov, Dirk Weissenborn, Xiaohua Zhai, Thomas Unterthiner, Mostafa Dehghani, Matthias Minderer, Georg Heigold, Sylvain Gelly, et al. An image is worth 16x16 words: Transformers for image recognition at scale. _arXiv preprint arXiv:2010.11929_ , 2020. 5 

- [15] Yao Feng, Vasileios Choutas, Timo Bolkart, Dimitrios Tzionas, and Michael J Black. Collaborative regression of expressive bodies using moderation. In _2021 International_ 

_Conference on 3D Vision (3DV)_ , pages 792–804. IEEE, 2021. 3, 6, 7 

- [16] Yao Feng, Weiyang Liu, Timo Bolkart, Jinlong Yang, Marc Pollefeys, and Michael J. Black. Learning disentangled avatars with hybrid 3d representations, 2023. 3 

- [17] Valentin Gabeur, Jean-S´ebastien Franco, Xavier Martin, Cordelia Schmid, and Gregory Rogez. Moulding humans: Non-parametric 3D human shape estimation from single images. In _ICCV_ , 2019. 3 

- [18] Chen Geng, Sida Peng, Zhen Xu, Hujun Bao, and Xiaowei Zhou. Learning neural volumetric representations of dynamic humans in minutes. In _CVPR_ , 2023. 3 

- [19] Michal Geyer, Omer Bar-Tal, Shai Bagon, and Tali Dekel. Tokenflow: Consistent diffusion features for consistent video editing. _arXiv preprint arXiv:2307.10373_ , 2023. 6 

- [20] Chen Guo, Tianjian Jiang, Xu Chen, Jie Song, and Otmar Hilliges. Vid2avatar: 3d avatar reconstruction from videos in the wild via self-supervised scene decomposition. In _Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR)_ , 2023. 3 

- [21] Sang-Hun Han, Min-Gyu Park, Ju Hong Yoon, Ju-Mi Kang, Young-Jae Park, and Hae-Gon Jeon. High-fidelity 3d human digitization from single 2k resolution images. In _Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR)_ , 2023. 3 

- [22] Kaiming He, Xiangyu Zhang, Shaoqing Ren, and Jian Sun. Deep residual learning for image recognition. In _Proceedings of the IEEE conference on computer vision and pattern recognition_ , pages 770–778, 2016. 5 

- [23] Tong He, John P. Collomosse, Hailin Jin, and Stefano Soatto. Geo-PIFu: Geometry and pixel aligned implicit functions for single-view human reconstruction. In _NeurIPS_ , 2020. 3 

- [24] Tong He, Yuanlu Xu, Shunsuke Saito, Stefano Soatto, and Tony Tung. ARCH++: Animation-Ready Clothed Human Reconstruction Revisited. In _ICCV_ , pages 11046–11056, 2021. 3 

- [25] Jonathan Ho, Ajay Jain, and Pieter Abbeel. Denoising diffusion probabilistic models. _Advances in neural information processing systems_ , 33:6840–6851, 2020. 2, 4 

- [26] Shoukang Hu, Fangzhou Hong, Liang Pan, Haiyi Mei, Lei Yang, and Ziwei Liu. Sherf: Generalizable human nerf from a single image. In _ICCV_ , 2023. 3 

- [27] Shuo Huang, Zongxin Yang, Liangting Li, Yi Yang, and Jia Jia. Avatarfusion: Zero-shot generation of clothingdecoupled 3d avatars using 2d diffusion. In _ACM MM_ , pages 5734–5745, 2023. 4 

- [28] Yangyi Huang, Hongwei Yi, Weiyang Liu, Haofan Wang, Boxi Wu, Wenxiao Wang, Binbin Lin, Debing Zhang, and Deng Cai. One-shot implicit animatable avatars with modelbased priors. In _IEEE Conference on Computer Vision (ICCV)_ , 2023. 3 

- [29] Yangyi Huang, Hongwei Yi, Yuliang Xiu, Tingting Liao, Jiaxiang Tang, Deng Cai, and Justus Thies. TeCH: Text-guided Reconstruction of Lifelike Clothed Humans. In _International Conference on 3D Vision (3DV)_ , 2024. 3, 6 

- [30] Zeng Huang, Yuanlu Xu, Christoph Lassner, Hao Li, and Tony Tung. ARCH: Animatable Reconstruction of Clothed Humans. In _CVPR_ , pages 8568–8576, 2020. 2 

9944 

- [31] Zeng Huang, Yuanlu Xu, Christoph Lassner, Hao Li, and Tony Tung. ARCH: Animatable Reconstruction of Clothed Humans. In _CVPR_ , pages 3093–3102, 2020. 3 

- [32] Boyi Jiang, Juyong Zhang, Yang Hong, Jinhao Luo, Ligang Liu, and Hujun Bao. BCNet: Learning body and cloth shape from a single image. In _ECCV_ , 2020. 3 

- [33] Tianjian Jiang, Xu Chen, Jie Song, and Otmar Hilliges. Instantavatar: Learning avatars from monocular video in 60 seconds. _arXiv_ , 2022. 3 

- [34] Wei Jiang, Kwang Moo Yi, Golnoosh Samei, Oncel Tuzel, and Anurag Ranjan. Neuman: Neural human radiance field from a single video. In _Proceedings of the European conference on computer vision (ECCV)_ , 2022. 3 

- [35] Justin Johnson, Alexandre Alahi, and Li Fei-Fei. Perceptual losses for real-time style transfer and super-resolution. _CoRR_ , abs/1603.08155, 2016. 6 

- [36] Hanbyul Joo, Tomas Simon, and Yaser Sheikh. Total capture: A 3d deformation model for tracking faces, hands, and bodies. In _CVPR_ , 2018. 3 

- [37] Angjoo Kanazawa, Michael J. Black, David W. Jacobs, and Jitendra Malik. End-to-end recovery of human shape and pose. In _CVPR_ , pages 7122–7131, 2018. 3 

- [38] Muhammed Kocabas, Nikos Athanasiou, and Michael J. Black. VIBE: Video inference for human body pose and shape estimation. In _CVPR_ , pages 5252–5262, 2020. 

- [39] Muhammed Kocabas, Chun-Hao P. Huang, Otmar Hilliges, and Michael J. Black. PARE: Part attention regressor for 3D human body estimation. In _ICCV_ , pages 11127–11137, 2021. 

- [40] Muhammed Kocabas, Chun-Hao P. Huang, Joachim Tesch, Lea M¨uller, Otmar Hilliges, and Michael J. Black. SPEC: Seeing people in the wild with an estimated camera. In _ICCV_ , pages 11035–11045, 2021. 

- [41] Nikos Kolotouros, Georgios Pavlakos, Michael J. Black, and Kostas Daniilidis. Learning to reconstruct 3D human pose and shape via model-fitting in the loop. In _ICCV_ , pages 2252–2261, 2019. 3 

- [42] Verica Lazova, Eldar Insafutdinov, and Gerard Pons-Moll. 360-Degree textures of people in clothing from a single image. In _International Conference on 3D Vision (3DV)_ , 2019. 3 

- [43] Jiefeng Li, Chao Xu, Zhicun Chen, Siyuan Bian, Lixin Yang, and Cewu Lu. HybrIK: A hybrid analytical-neural inverse kinematics solution for 3D human pose and shape estimation. In _CVPR_ , pages 3383–3393, 2021. 3 

- [44] Jiefeng Li, Siyuan Bian, Qi Liu, Jiasheng Tang, Fan Wang, and Cewu Lu. NIKI: Neural inverse kinematics with invertible neural networks for 3d human pose and shape estimation. In _CVPR_ , 2023. 3 

- [45] Jiahao Li, Zongxin Yang, Xiaohan Wang, Jianxin Ma, Chang Zhou, and Yi Yang. Jotr: 3d joint contrastive learning with transformers for occluded human mesh recovery. In _ICCV_ , pages 9110–9121, 2023. 3 

- [46] Zhihao Li, Jianzhuang Liu, Zhensong Zhang, Songcen Xu, and Youliang Yan. CLIFF: Carrying Location Information in Full Frames into Human Pose and Shape Estimation. In _ECCV_ , pages 590–606. Springer, 2022. 3 

- [47] Tingting Liao, Xiaomei Zhang, Yuliang Xiu, Hongwei Yi, Xudong Liu, Guo-Jun Qi, Yong Zhang, Xuan Wang, Xiangyu Zhu, and Zhen Lei. High-Fidelity Clothed Avatar Reconstruction from a Single Image. In _CVPR_ , 2023. 3 

- [48] Chen-Hsuan Lin, Jun Gao, Luming Tang, Towaki Takikawa, Xiaohui Zeng, Xun Huang, Karsten Kreis, Sanja Fidler, Ming-Yu Liu, and Tsung-Yi Lin. Magic3d: High-resolution text-to-3d content creation. In _IEEE Conference on Computer Vision and Pattern Recognition (CVPR)_ , 2023. 2 

- [49] Minghua Liu, Chao Xu, Haian Jin, Linghao Chen, Mukund Varma T, Zexiang Xu, and Hao Su. One-2-3-45: Any single image to 3d mesh in 45 seconds without pershape optimization, 2023. 

- [50] Ruoshi Liu, Rundi Wu, Basile Van Hoorick, Pavel Tokmakov, Sergey Zakharov, and Carl Vondrick. Zero-1-to-3: Zero-shot one image to 3d object, 2023. 7 

- [51] Yuan Liu, Cheng Lin, Zijiao Zeng, Xiaoxiao Long, Lingjie Liu, Taku Komura, and Wenping Wang. Syncdreamer: Learning to generate multiview-consistent images from a single-view image. _arXiv preprint arXiv:2309.03453_ , 2023. 2 

- [52] Matthew Loper, Naureen Mahmood, Javier Romero, Gerard Pons-Moll, and Michael J. Black. SMPL: A skinned multiperson linear model. _ACM TOG_ , 34(6):248:1–248:16, 2015. 3, 4 

- [53] William E Lorensen and Harvey E Cline. Marching cubes: A high resolution 3d surface construction algorithm. _ACM siggraph computer graphics_ , 21(4):163–169, 1987. 5 

- [54] Fan Ma, Xiaojie Jin, Heng Wang, Yuchen Xian, Jiashi Feng, and Yi Yang. Vista-llama: Reliable video narrator via equal distance to visual tokens. In _CVPR_ , 2024. 5 

- [55] Qianli Ma, Jinlong Yang, Anurag Ranjan, Sergi Pujades, Gerard Pons-Moll, Siyu Tang, and Michael J. Black. Learning to Dress 3D People in Generative Clothing. In _Computer Vision and Pattern Recognition (CVPR)_ , 2020. 6 

- [56] Jiteng Mu, Shen Sang, Nuno Vasconcelos, and Xiaolong Wang. ActorsNeRF: animatable few-shot human rendering with generalizable nerfs. pages 18391–18401, 2023. 3 

- [57] Alexander Quinn Nichol and Prafulla Dhariwal. Improved denoising diffusion probabilistic models. In _International Conference on Machine Learning_ , pages 8162–8171. PMLR, 2021. 2, 4 

- [58] OpenAI. Gpt-4 technical report. _ArXiv_ , abs/2303.08774, 2023. 5 

- [59] Xiao Pan, Zongxin Yang, Jianxin Ma, Chang Zhou, and Yi Yang. Transhuman: A transformer-based human representation for generalizable neural human rendering. In _Proceedings of the IEEE/CVF International Conference on Computer Vision (ICCV)_ , pages 3544–3555, 2023. 3 

- [60] Georgios Pavlakos, Vasileios Choutas, Nima Ghorbani, Timo Bolkart, Ahmed AA Osman, Dimitrios Tzionas, and Michael J Black. Expressive body capture: 3d hands, face, and body from a single image. In _CVPR_ , pages 10975– 10985, 2019. 3 

- [61] Georgios Pavlakos, Vasileios Choutas, Nima Ghorbani, Timo Bolkart, Ahmed A. A. Osman, Dimitrios Tzionas, and Michael J. Black. Expressive body capture: 3D hands, face, 

9945 

and body from a single image. In _Proceedings IEEE Conf. on Computer Vision and Pattern Recognition (CVPR)_ , pages 10975–10985, 2019. 2, 4, 5, 8 

- [62] Sida Peng, Junting Dong, Qianqian Wang, Shangzhan Zhang, Qing Shuai, Xiaowei Zhou, and Hujun Bao. Animatable neural radiance fields for modeling dynamic human bodies. In _Proceedings of the IEEE/CVF International Conference on Computer Vision (ICCV)_ , pages 14314–14323, 2021. 3 

- [63] Sida Peng, Yuanqing Zhang, Yinghao Xu, Qianqian Wang, Qing Shuai, Hujun Bao, and Xiaowei Zhou. Neural body: Implicit neural representations with structured latent codes for novel view synthesis of dynamic humans. In _Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR)_ , pages 9054–9063, 2021. 3 

- [64] Ben Poole, Ajay Jain, Jonathan T. Barron, and Ben Mildenhall. Dreamfusion: Text-to-3d using 2d diffusion. _arXiv_ , 2022. 2 

- [65] Guocheng Qian, Jinjie Mai, Abdullah Hamdi, Jian Ren, Aliaksandr Siarohin, Bing Li, Hsin-Ying Lee, Ivan Skorokhodov, Peter Wonka, Sergey Tulyakov, and Bernard Ghanem. Magic123: One image to high-quality 3d object generation using both 2d and 3d diffusion priors. _arXiv preprint arXiv:2306.17843_ , 2023. 2 

- [66] Alec Radford, Jong Wook Kim, Chris Hallacy, Aditya Ramesh, Gabriel Goh, Sandhini Agarwal, Girish Sastry, Amanda Askell, Pamela Mishkin, Jack Clark, et al. Learning transferable visual models from natural language supervision. In _International conference on machine learning_ . PMLR, 2021. 3 

- [67] Elad Richardson, Gal Metzer, Yuval Alaluf, Raja Giryes, and Daniel Cohen-Or. Texture: Text-guided texturing of 3d shapes. _arXiv preprint arXiv:2302.01721_ , 2023. 7 

- [68] Robin Rombach, Andreas Blattmann, Dominik Lorenz, Patrick Esser, and Bj¨orn Ommer. High-resolution image synthesis with latent diffusion models, 2021. 3 

- [69] Shunsuke Saito, Zeng Huang, Ryota Natsume, Shigeo Morishima, Hao Li, and Angjoo Kanazawa. PIFu: Pixel-aligned implicit function for high-resolution clothed human digitization. In _ICCV_ , pages 2304–2314, 2019. 2, 3, 5, 6, 7 

- [70] Shunsuke Saito, Tomas Simon, Jason Saragih, and Hanbyul Joo. PIFuHD: Multi-Level Pixel-Aligned Implicit Function for High-Resolution 3D Human Digitization. In _CVPR_ , pages 81–90, 2020. 2, 3, 6, 7 

- [71] Xiaolong Shen, Zongxin Yang, Xiaohan Wang, Jianxin Ma, Chang Zhou, and Yi Yang. Global-to-local modeling for video-based 3d human pose and shape estimation. In _CVPR_ , pages 8887–8896, 2023. 3 

- [72] David Smith, Matthew Loper, Xiaochen Hu, Paris Mavroidis, and Javier Romero. FACSIMILE: Fast and accurate scans from an image in less than a second. In _ICCV_ , 2019. 3 

- [73] Jascha Sohl-Dickstein, Eric Weiss, Niru Maheswaranathan, and Surya Ganguli. Deep unsupervised learning using nonequilibrium thermodynamics. In _International conference on machine learning_ , pages 2256–2265. PMLR, 2015. 2, 4 

- [74] Jiaming Song, Chenlin Meng, and Stefano Ermon. Denoising diffusion implicit models. In _International Conference on Learning Representations_ , 2020. 6 

- [75] Jiaxiang Tang, Jiawei Ren, Hang Zhou, Ziwei Liu, and Gang Zeng. Dreamgaussian: Generative gaussian splatting for efficient 3d content creation. _arXiv preprint arXiv:2309.16653_ , 2023. 6, 7 

- [76] Junshu Tang, Tengfei Wang, Bo Zhang, Ting Zhang, Ran Yi, Lizhuang Ma, and Dong Chen. Make-it-3d: High-fidelity 3d creation from a single image with diffusion prior. _arXiv preprint arXiv:2303.14184_ , 2023. 2 

- [77] Ashish Vaswani, Noam Shazeer, Niki Parmar, Jakob Uszkoreit, Llion Jones, Aidan N Gomez, Łukasz Kaiser, and Illia Polosukhin. Attention is all you need. _Advances in neural information processing systems_ , 30, 2017. 2, 5 

- [78] Chung-Yi Weng, Brian Curless, Pratul P. Srinivasan, Jonathan T. Barron, and Ira Kemelmacher-Shlizerman. HumanNeRF: Free-viewpoint rendering of moving people from monocular video. In _Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR)_ , pages 16210–16220, 2022. 3 

- [79] Jay Zhangjie Wu, Yixiao Ge, Xintao Wang, Stan Weixian Lei, Yuchao Gu, Yufei Shi, Wynne Hsu, Ying Shan, Xiaohu Qie, and Mike Zheng Shou. Tune-a-video: One-shot tuning of image diffusion models for text-to-video generation. In _Proceedings of the IEEE/CVF International Conference on Computer Vision_ , pages 7623–7633, 2023. 6 

- [80] Donglai Xiang, Fabian Prada, Chenglei Wu, and Jessica K. Hodgins. MonoClothCap: Towards temporally coherent clothing capture from monocular RGB video. In _International Conference on 3D Vision (3DV)_ , 2020. 3 

- [81] Yuliang Xiu, Jinlong Yang, Dimitrios Tzionas, and Michael J. Black. ICON: Implicit Clothed humans Obtained from Normals. In _CVPR_ , 2022. 2, 3, 6, 7 

- [82] Yuliang Xiu, Jinlong Yang, Xu Cao, Dimitrios Tzionas, and Michael J. Black. ECON: Explicit Clothed humans Optimized via Normal integration. In _CVPR_ , 2023. 2, 3, 5, 6 

- [83] Hongyi Xu, Eduard Gabriel Bazavan, Andrei Zanfir, William T. Freeman, Rahul Sukthankar, and Cristian Sminchisescu. GHUM & GHUML: Generative 3D human shape and articulated pose models. In _CVPR_ , pages 6183–6192, 2020. 3 

- [84] Yuanyou Xu, Zongxin Yang, and Yi Yang. Seeavatar: Photorealistic text-to-3d avatar generation with constrained geometry and appearance. _arXiv preprint arXiv:2312.08889_ , 2023. 4 

- [85] Xueting Yang, Yihao Luo, Yuliang Xiu, Wei Wang, Hao Xu, and Zhaoxin Fan. D-if: Uncertainty-aware human digitization via implicit distribution field. In _Proceedings of the IEEE/CVF International Conference on Computer Vision_ , pages 9122–9132, 2023. 2, 3, 6 

- [86] Zongxin Yang, Guikun Chen, Xiaodi Li, Wenguan Wang, and Yi Yang. Doraemongpt: Toward understanding dynamic scenes with large language models. _arXiv preprint arXiv:2401.08392_ , 2024. 6 

- [87] Tao Yu, Zerong Zheng, Kaiwen Guo, Pengpeng Liu, Qionghai Dai, and Yebin Liu. Function4d: Real-time human volumetric capture from very sparse consumer rgbd sensors. In 

9946 

_IEEE Conference on Computer Vision and Pattern Recognition (CVPR2021)_ , 2021. 3, 6, 7 

- [88] Zhengming Yu, Wei Cheng, Xian Liu, Wayne Wu, and Kwan-Yee Lin. Monohuman: Animatable human neural field from monocular video. _CVPR_ , 2023. 3 

- [89] Ilya Zakharkin, Kirill Mazur, Artur Grigorev, and Victor Lempitsky. Point-based modeling of human clothing. In _ICCV_ , 2021. 3 

- [90] Hongwen Zhang, Yating Tian, Xinchi Zhou, Wanli Ouyang, Yebin Liu, Limin Wang, and Zhenan Sun. PyMAF: 3D Human Pose and Shape Regression with Pyramidal Mesh Alignment Feedback Loop. In _ICCV_ , 2021. 3 

- [91] Hongwen Zhang, Yating Tian, Yuxiang Zhang, Mengcheng Li, Liang An, Zhenan Sun, and Yebin Liu. PyMAF-X: Towards Well-aligned Full-body Model Regression from Monocular Images. _IEEE TPAMI_ , 2023. 3 

- [92] Zechuan Zhang, Li Sun, Zongxin Yang, Ling Chen, and Yi Yang. Global-correlated 3d-decoupling transformer for clothed avatar reconstruction. In _Advances in Neural Information Processing Systems (NeurIPS)_ , 2023. 2, 3, 5, 6 

- [93] Zerong Zheng, Tao Yu, Yebin Liu, and Qionghai Dai. PaMIR: Parametric Model-conditioned Implicit Representation for image-based human reconstruction. _IEEE TPAMI_ , 44(6):3170–3184, 2021. 2, 3, 6 

- [94] Hao Zhu, Xinxin Zuo, Sen Wang, Xun Cao, and Ruigang Yang. Detailed human shape estimation from a single image by hierarchical mesh deformation. In _CVPR_ , 2019. 3 

9947 

