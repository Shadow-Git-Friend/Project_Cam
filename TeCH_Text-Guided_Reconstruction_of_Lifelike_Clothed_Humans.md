2024 International Conference on 3D Vision (3DV) 

## **TeCH: Text-Guided Reconstruction of Lifelike Clothed Humans** 

Yangyi Huang[1] _[∗]_ , Hongwei Yi[2] _[∗]_ , Yuliang Xiu[2] _[∗]_ , Tingting Liao[3] , Jiaxiang Tang[4] , Deng Cai[1] , Justus Thies[2] 

1State Key Lab of CAD & CG, Zhejiang University 2Max Planck Institute for Intelligent Systems 3Mohamed bin Zayed University of Artificial Intelligence 4Peking University huangyangyi@zju.edu.cn, _{_ hongwei.yi, yuliang.xiu, justus.thies _}_ @tuebingen.mpg.de tingting.liao@mbzuai.ac.ae, tjx@pku.edu.cn, dengcai@cad.zju.edu.cn 

Figure 1. Given a single image, TeCH reconstructs a lifelike 3D clothed human. **“Lifelike”** refers to 1) a detailed full-body geometry, including facial features and clothing wrinkles, in both frontal and unseen regions, and 2) a high-quality texture with consistent color and intricate patterns. The key insight is to guide the reconstruction using a personalized Text-to-Image (T2I) diffusion model and textual information derived via visual questioning answering (VQA). Multi-view supervision is established through Score Distillation Sampling (SDS). 

## **Abstract** 

_Despite recent research advancements in reconstructing clothed humans from a single image, accurately restoring the “unseen regions” with high-level details remains an unsolved challenge that lacks attention. Existing methods often generate overly smooth back-side surfaces with a blurry texture. But how to effectively capture all visual attributes of an individual from a single image, which are sufficient to reconstruct unseen areas (_ e.g _. the back view)? Motivated by the power of foundation models, TeCH reconstructs the 3D human by leveraging 1) descriptive text prompts (_ e.g _. garments, colors, hairstyles) which are automatically generated via a garment parsing model and Visual Question Answering (VQA), 2) a personalized finetuned Text-to-Image diffusion model (T2I) which learns the_ 

_“indescribable” appearance. To represent high-resolution 3D clothed humans at an affordable cost, we propose a hybrid 3D representation based on DMTet, which consists of an explicit body shape grid and an implicit distance field. Guided by the descriptive prompts + personalized T2I diffusion model, the geometry and texture of the 3D humans are optimized through multi-view Score Distillation Sampling (SDS) and reconstruction losses based on the original observation. TeCH produces high-fidelity 3D clothed humans with consistent & delicate texture, and detailed full-body geometry. Quantitative and qualitative experiments demonstrate that TeCH outperforms the state-of-the-art methods in terms of reconstruction accuracy and rendering quality. The code will be publicly available for research purposes at huangyangyi.github.io/TeCH_ 

> *These authors contributed equally to this work. 

979-8-3503-6245-9/24/$31.00 ©2024 IEEE DOI 10.1109/3DV62453.2024.00152 

1531 

Authorized licensed use limited to: Nazarbayev University. Downloaded on June 30,2026 at 07:49:14 UTC from IEEE Xplore.  Restrictions apply. 

## **1. Introduction** 

High-fidelity 3D digital humans are crucial for various applications in augmented and virtual reality, such as gaming, social media, education, e-commerce, and immersive telepresence. To facilitate the creation of digital humans from easily accessible in-the-wild photos, numerous approaches focus on reconstructing a 3D clothed human shape from a single image [12, 39, 40, 48, 72, 78, 111–113, 130– 132, 151]. However, despite the advancements made by previous approaches, this specific problem can be considered ill-posed due to the lack of observations of non-visible areas. Efforts to predict _invisible_ regions ( _e.g_ . back-side) based on _visible_ visual cues ( _e.g_ . colors [5, 48, 112], normal estimates [113, 131, 132]) have proven unsuccessful, resulting in the blurry texture and smoothed-out geometry, see Fig. 7. As a result, inconsistencies arise when observing these reconstructions from different angles. To address this issue, introducing multi-view supervision could be a potential solution. But is it feasible given only a single input image? Here, we propose TeCH to answer this question. Unlike prior research that primarily explores the connection between visible frontal cues and non-visible regions, TeCH integrates textual information derived from the input image with a personalized Text-to-Image diffusion model, _i.e_ ., DreamBooth [110], to guide the reconstruction process. 

Specifically, we divide the information from the single input image into the semantic information that can be accurately described by texts and subject’s distinctive and finedetailed appearance which is not easily describable by text: **1) Describable** semantic prompts, including the detailed descriptions of colors, styles of garments, hairstyles, and facial features, are _explicitly_ parsed from the input image using a garment parsing model ( _i.e_ ., SegFormer [127]) and a pre-trained visual-language VQA model ( _i.e_ ., BLIP [70]). **2) Indescribable** appearance information, which _implicitly_ specifies the subject’s distinctive appearance and finegrained details, is embedded into a unique token “[ _V_ ]”, by a personalized Text-to-Image (T2I) diffusion model [110]. 

Based on these information sources, we optimize the 3D human using multi-view Score Distillation Sampling (SDS)[103], reconstruction losses based on the original observations, and regularization obtained from off-the-shelf normal estimators, to enhance the fidelity of the reconstructed 3D human models while preserving their original identity. To represent a high-resolution geometry at an affordable cost, we propose a hybrid 3D representation based on DMTet [33, 115]. This hybrid 3D representation combines an explicit tetrahedral grid to approximate the overall body shape and implicit Signed Distance Function (SDF) and RGB fields to capture fine details in geometry and texture. In a two-stage optimization process, we first optimize this tetrahedral grid, extract the geometry represented as a mesh, and then optimize the texture. 

TeCH enables the reconstruction of high-fidelity 3D clothed humans with detailed full-body geometry, and intricate textures with consistent color and patterns. As a result, it facilitates various downstream applications such as novel view rendering, character animation, and shape & texture editing. Quantitative evaluations performed on 3D clothed human datasets, covering various poses (CAPE [102]) and outfits (THuman2.0 [138]), have demonstrated TeCH’s superiority in reconstructing geometric details. Qualitative comparisons conducted on in-the-wild images, accompanied by a perceptual study, further confirm that TeCH surpasses SOTA methods in terms of rendering quality. 

## **2. Related Work** 

TeCH **reconstructs** a high-fidelity clothed human from a single image, and **imagines** the missing parts with descriptive prompts and a personalized diffusion model. We relate TeCH to both image-based human reconstructors (Sec. 2.1) and 3D human generators (Sec. 2.2). In Appendix A, we additionally review “image-to-general-3D-content” works. 

## **2.1. Image-based Clothed Human Reconstruction** 

**Explicit-shape-based Methods** . Human Mesh Recovery (HMR) from a single RGB image is a long-standing problem that has been thoroughly explored. Many methods [26, 55, 61–64, 69, 71, 74, 142, 144] use mesh-based parametric body models [53, 87, 101, 134] to regress the shape and pose of minimally clothed 3D body meshes. To account for the 3D garments, 3D clothing offsets [1– 4, 68, 126, 154] or deformable garment templates [9, 51] are used on top of a body model. Also, non-parametric explicit representations, such as depth maps [30, 118], normal maps [132], and point clouds [140] could be leveraged to reconstruct the clothed human. However, explicit shapes often suffer from restricted topological flexibility, particularly, when dealing with outfit variations in real-world scenarios. 

**Implicit-function-based Methods** . Implicit representations (occupancy/distance field) are topology-agnostic, and thus, can represent 3D clothed humans, with arbitrary topologies, such as open jackets and loose skirts. A line of works regresses the free-form implicit surface in an endto-end manner [5, 112, 113], leverages a 3D geometric prior [12, 21, 39, 40, 48, 78, 131, 136, 151], or progressively builds up the 3D human using a “sandwich-like” structure and implicit shape completion [132]. Among these works, PIFu [112], ARCH(++) [40, 48], and PaMIR [151] infer the full texture from the input image. PHORHUM [5] and S3F [21] additionally decompose the albedo and global illumination. However, the lack of multi-view supervision often results in depth ambiguities or inconsistent textures. 

**NeRF-based Methods** . There is a separate line of research that focuses on optimizing neural radiance fields (NeRF) 

1532 

Authorized licensed use limited to: Nazarbayev University. Downloaded on June 30,2026 at 07:49:14 UTC from IEEE Xplore.  Restrictions apply. 

Figure 2. **Method overview.** TeCH takes an image _I_ of a human as input. Text guidance is constructed through **(a)** using garment parsing model (SegFormer) and VQA model (BLIP) to parse the human attributes _A_ with pre-defined problems _Q_ , and **(b)** embedding with subjectspecific appearance into DreamBooth _D[′]_ as unique token [ _V_ ]. Next, TeCH represents the 3D clothed human with **(c)** SMPL-X initialized hybrid DMTet, and optimize both geometry and texture using _L_ SDS guided by prompt _P_ = [ _V_ ] + _P_ VQA( _A_ ). During the optimization, _L_ recon is introduced to ensure input view consistency, _L_ CD is to enforce the color consistency between different views, and _L_ normal serves as surface regularizer. Finally, the extracted high-quality textured meshes **(d)** are ready to be used in various downstream applications. 

from a single image. SHERF [45] and ELICIT [47] optimize a generalized human NeRF, incorporating modelbased priors (SMPL-X [101]). While SHERF complements missing information from partial 2D observations, ELICIT leverages appearance prior from CLIP [106]. 

## **2.2. Generative Modeling of 3D Clothed Humans** 

**3D Human Generator Trained on 3D Data** . Statistical body models [53, 87, 101, 134] can be considered as 3D generative models of the human body. These models are trained on numerous 3D scans of minimally clothed bodies, and can generate posed bodies with varying shapes, but without clothing. To account for the outfits, CAPE [88] learns a clothing offset layer based on the SMPL-D model, from registered human scans, Chupa [58] “carves” the SMPL mesh by dual normal maps generated by poseconditioned diffusion model; Alternatively, gDNA [17], NPMs [97], NSF [135], and SPAMs [98], learn the implicit clothed avatars from normalized raw captures ( _i.e_ ., scans, depth maps). Unfortunately, all the aforementioned methods of learning generative 3D humans with diverse shapes and appearances require 3D data, which is both limited and expensive to acquire. Rodin [123] has recently employed large-scale 3D synthetic head avatars in combination with a diffusion model to develop a high-fidelity head avatar generator. However, the scarcity of datasets containing real 3D clothed humans [11, 18, 49, 129, 138, 149, 150] limits the model’s generalization ability and may lead to overfitting on constrained datasets. 

**3D Human Generator from 2D Image Collections** . In contrast to 3D data, large-scale 2D human images are widely available from DeepFashion [35, 85], SHHQ [29] and LAION-5B [114]. Related human generators represent 3D humans using meshes [37, 41, 52], DMTet [34], Tri-planes [8, 25, 94, 119, 146], implicit functions [128], 

or neural fields [13, 42, 65, 79, 141]. Some methods adapt GANs [56] by integrating diff-renderer [8, 25, 37, 94, 119, 120, 128, 146], while others leverage diffusion models [13, 41, 46, 65, 143, 145]. Despite the demonstrated quality of these methods in generating textured avatars, a gap still exists in achieving “lifelike” avatars with detailed geometry and texture, consistent with the input. 

In contrast, TeCH excels at generating “lifelike” 3D characters from a single image, incorporating consistent texture with intricate patterns like checkered or overlapped designs. It relies on a pretrained diffusion model which is trained on a billion-level data, LAION-5B [114], and offers the ability to **imagine the non-visible regions** , guided by descriptive prompts. Furthermore, it leverages the imagebased reconstruction approach to faithfully **reconstruct the visible regions** from a single input image. 

## **3. Method** 

Given a single image as input, TeCH aims at reconstructing a high-fidelity 3D clothed human. As depicted in Fig. 2, TeCH follows a two-step procedure: Firstly, a text prompt that describes the human in the input image is obtained via the human parsing model SegFormer [127] and the VQA model BLIP [70] (Sec. 3.1). This descriptive prompt is used to guide the generation process in DreamBooth [110], a personalized Text-to-Image diffusion model fine-tuned on augmented input images. Secondly, the 3D human, which is represented as hybrid DMTet and initialized with SMPL-X (Sec. 3.2), is optimized with Score Distillation Sampling (SDS) losses [103] computed from the personalized DreamBooth (Sec. 3.3). Note that the SDS loss has been introduced in DreamFusion [103] for the task of Textto-3D generation of general objects, by optimizing a neural radiance field (NeRF) with gradients from a frozen diffusion model. For these preliminaries, we refer to Appendix B. 

1533 

Authorized licensed use limited to: Nazarbayev University. Downloaded on June 30,2026 at 07:49:14 UTC from IEEE Xplore.  Restrictions apply. 

## **3.1. Extracting Text-guidance from the Observation** 

**Parsing human attributes** . As depicted in Fig. 3, given the input image of a human, SegFormer [127], which is finetuned on the ATR dataset [76, 77], is applied to recognize each part of the garments ( _e.g_ . hat, skirt, pants, belt, shoes). To obtain detailed descriptions of the parsed garments, we utilize the vision-language model BLIP [70] as VQA captioner. This model has been pre-trained on a vast collection of image-text pairs, enabling it to automatically generate descriptive prompts. Rather than using naive image captioning, we employ a series of fine-grained VQA questions _{Qi}_ as input to BLIP (see Appendix C). These questions cover garment styles, colors, facial features, and hairstyles, with the corresponding answers denoted as _{Ai}_ . The set of _{Ai}_ is inserted into a predefined template to create text prompts _P_ VQA, which will serve as text-guidance to condition the text-to-image diffusion model. 

**Embedding subject-specific appearance** . Does the text prompt _P_ VQA comprehensively capture all the visual characteristics of the subject? No, a picture is worth a thousand words. Thus, we utilize DreamBooth [110] to learn the _indescribable_ visual appearance. DreamBooth is a method for “personalizing” a diffusion model through few-shot tuning (3 _∼_ 5 images). We perform DreamBooth’s fine-tuning on a pre-trained Stable Diffusion (v1.5) as the base model. To generate the needed inputs, we augment the single input image with five different backgrounds, as shown in Fig. 3. To prevent language drift, we assign the subject classes “man” or “woman” based on the gender determined by the VQA. After fine-tuning DreamBooth, the subject-specific distinctive appearance is encoded within a unique identifier token “[ _V_ ]”. We insert “[ _V_ ]” into the prompt _P_ VQA, to construct the final text prompt _P_ used by the personalized DreamBooth _D[′]_ . In Fig. 4, you can see how these individual prompts contribute to the final appearance, additional information are provided in Appendix D. 

## **3.2. Hybrid 3D Representation** 

To efficiently represent the 3D clothed human at a high resolution, we embed DMTet [33, 115] around the SMPL-X body mesh [95]. Specifically, we construct a compact tetrahedral grid ( _V_ shell _, T_ shell) within an outer shell _M_ shell, shown in Fig. 2-(c). Compared to the DMTet cubic-based tetrahedral grid, the outer shell tetrahedral grid is more computationally efficient for high-resolution geometry modeling of a human. Using PIXIE [26], we estimate an initial body _M_ body. To create _M_ shell, a series of mesh dilation, down-sampling, and up-sampling steps are applied to the body mesh _M_ body (see details in Appendix E). 

We use two MLP networks Ψg _,_ Ψc with hash encoding [92], parameterized by _ψg_ and, _ψc_ to learn the geometry and color separately. The geometry network Ψg predicts the 

Figure 3. **Prompt construction (** _P_ = _P_ VQA + [ _V_ ] **).** (a) Inquire VQA model with predefined questions on individual appearance to construct _describable_ prompts _P_ VQA. (b) Fine-tuned DreamBooth with background-augmented images to embed _indescribable_ subject-specific details into unique identifier [ _V_ ]. 

Figure 4. **The effects of text guidance.** We compare the effectiveness of using only VQA descriptions (TeCHvqa), only DreamBooth identity token (TeCHdb), and both of them (TeCH). 

SDF value Ψg( _vi_ ) = _s_ ( _vi_ ; _ψ_ g) of each DMTet vertex _vi_ . It is initialized by fitting it to the SDF of _M_ shell: 

**==> picture [194 x 23] intentionally omitted <==**

where **P** = _{pi ∈_ R[3] _}_ is a point set randomly sampled near _M_ shell, and SDF( _pi_ ) is the pre-computed pointwise SDF. Triangular meshes can be extracted from this efficient hybrid 3D representation by Marching Tetrahedra (MT) [24]: 

**==> picture [192 x 12] intentionally omitted <==**

Given the camera parameters **k** , the generated mesh is rendered through differentiable rasterization _R_ [67], to get the back-projected 3D locations _P_ ( _M,_ **k** ), rendered mask _M_ ( _M,_ **k** ), and rendered normal image _N_ ( _M,_ **k** ): 

**==> picture [208 x 11] intentionally omitted <==**

The albedo of each back-projected pixel is predicted by the color network Ψ **c** , where _ψ_ c represents the parameters: 

**==> picture [186 x 11] intentionally omitted <==**

As detailed in Sec. 3.3, we optimize this 3D representation using a coarse-to-fine strategy by applying successive subdivisions on the tetrahedral grids. Specifically, a 

1534 

Authorized licensed use limited to: Nazarbayev University. Downloaded on June 30,2026 at 07:49:14 UTC from IEEE Xplore.  Restrictions apply. 

more detailed surface _M_ subdiv( _ψ_ g) can be obtained by applying volume subdivision on the surface tetrahedral grids ( _V_ surface _, T_ surface) that intersect with _M_ ( _ψ_ g). Note that the SDF values of the refined vertices are still inferred by Ψg. 

## **3.3. Multi-stage Optimization** 

We adopt a multi-stage, coarse-to-fine optimization process to sequentially recover the subject’s geometry and texture. In the initial stage, we utilize the tetrahedral representation to model the subject’s geometry (Sec. 3.3.1). Next, the appearance is recovered using the mesh that is extracted from the tetrahedral grid (Sec. 3.3.2). Both stages leverage SDS-based losses using the personalized DreamBooth model, which provides multi-view supervision by sampling new camera views as described in Sec. 3.3.3. 

## **3.3.1 Geometry Stage** 

We optimize the geometry based on a silhouette loss _L_ sil using the orig. image, a text-guided SDS loss on rendered normal images _L_[norm] SDS[, and geometric regularization] _[ L]_[reg][ based] on pred. normals _L_ norm and surface smoothness _L_ lap: 

**==> picture [201 x 26] intentionally omitted <==**

where _λ_ represents the weights to balance the losses. During optimization of this loss, we perform a coarse-tofine subdivision on DMTet, to robustly produce a highresolution mesh for the clothed body. Specifically, the optimization is first performed w/o subdivision for _t_ coarse = 5000 iters, and then with subdivision for _t_ = 5000 iters. 

**Pixel-aligned silhouette loss** . The silhouette loss [137, 147] enforces pixel-alignment with the foreground mask _S_ of the input image _I_ under the input camera view **k** : 

**==> picture [200 x 42] intentionally omitted <==**

It consists of (1) a pixel-wise L2 loss over the foreground mask _S_ and the rendered silhouette _M_ , and (2) an edge distance loss, based on the distance of each silhouette boundary pixel _x ∈_ Edge( _M_ ( _M,_ **k** )) to the nearest foreground mask boundary pixel _x_ ˆ _∈_ Edge( _S_ ). 

**SDS loss on normal images** . Inspired by Fantasia3D [16], our approach integrates normal renderings with the SDS loss [103]. It enables TeCH to effectively capture intricate geometric details without rendering the color image. Given the surface normals **n** = _N_ ( _M,_ **k** ), _L_[norm] SDS[is][defined][as:] 

Figure 5. **The effects of normal regularization.** _L_ norm regularizes the surface with predicted normal images _N_[ˆ] front _, N_[ˆ] back. 

**==> picture [223 x 41] intentionally omitted <==**

where **c** _[P]_[norm] is the text condition with an augmented prompt _P_ norm. We construct _P_ norm from _P_ by adding an extra description “a detailed sculpture of” to better reflect the intrinsic characteristics of normal maps. 

**Geometric regularization** . We found that relying solely on silhouette and SDS losses may lead to the generation of noisy surfaces, which is particularly evident for subjects wearing complex clothing. To address this, we leverage normal estimations as an additional constraint to regularize the reconstructed surface (see Fig. 5): 

**==> picture [223 x 30] intentionally omitted <==**

where _N_[ˆ] **k** are the front and back normal maps _estimated_ by ICON [131] indexed by the view **k** ( **k** _∈{_ front _,_ back _}_ ). **n** are the corresponding _rendered_ normal images of the 3D shape Ψg.We use a combination of LPIPS and MSE loss to enhance the similarity between _N_[ˆ] **k** and **n** . Furthermore, we utilize a Laplacian smoothing [6] regularizer, as _L_ lap. 

**Mesh extraction** . We use Marching Tetrahedra [24] to extract the mesh from the tetrahedral grid. Like ECON [132], we register SMPL-X to this mesh, which allows us to transfer skinning weights for animation (see Fig. 10). In addition, we replace the hands with SMPL-X ones which effectively mitigates the artifacts introduced during reposing, which is needed in the subsequent texture generation stage. 

## **3.3.2 Texture Stage** 

Given the triangular mesh from the geometry stage, we optimize the full texture. To recover the consistent details and color, even for self-occluded regions, we render both the input pose ( _M_ in) and the A-pose ( _M_ A) during optimization. The textures of _M_ in and _M_ A are modeled by Ψcolor in the 3D space of _M_ A. We optimize the texture from scratch with _ψ_ c randomly initialized. In Fig. 6, we show the effect of this 

1535 

Authorized licensed use limited to: Nazarbayev University. Downloaded on June 30,2026 at 07:49:14 UTC from IEEE Xplore.  Restrictions apply. 

disparity between the color distributions of the real and rendered images using a Chamfer Distance (CD) by treating the pixels as points within the RGB color space: 

Figure 6. **The effects of color consistency loss** _L_ CD **and multipose training (** _M_ A **) for texture optimization.** _L_ CD corrects the over-saturated back-side color generated by SDS, while _M_ A improves the texture quality under self-occlusion or extreme poses. 

multi-pose training. We utilize an occlusion-aware reconstruction loss _L_ recon on the input view of _M_ in, an SDS loss _L_[color] SDS[with text guidance on rendered color images of both] _M_ in and _M_ A, and a color consistency regularization _L_ CD, with respective weights _λ_ to balance the individual losses: 

**==> picture [224 x 13] intentionally omitted <==**

Note that _L_ CD is only utilized after the full-body texture convergence (5000 iters), in an additional optimization phase of 2000 iterations for enforcing color consistency. 

**Occlusion-aware reconstruction loss** . We apply an input view reconstruction loss _L_ recon to minimize the difference between input image _I_ and the rendered image _I[′]_ ( _M, ψ_ c _,_ **k** _I_ ). Self-occluded areas may lead to incorrect texture due to geometry misalignment, thus, an occlusionaware mask _m_ occ is introduced: 

**==> picture [213 x 28] intentionally omitted <==**

where **k** _I_ denotes the input view camera, and _λ_ MSE is a weight to balance the two loss terms. 

**SDS loss on color images** . To recover the full-body texture, including unseen regions, we update _ψ_ c via SDS loss _L_[color] SDS with text guidance. This loss is calculated based on randomview color renderings **x** = _I[′]_ ( _ψ_ g _, ψ_ c _,_ **k** ), and DreamBooth _D[′]_ parameterized by _φ[′]_ and guided by text prompt _P_ . 

**==> picture [223 x 41] intentionally omitted <==**

where **k** is the camera pose, **c** _[P]_ is the text embedding of _P_ . 

**Chamfer-based color consistency loss** . As mentioned in DreamFusion [103], the SDS loss may result in oversaturated colors, which will cause a noticeable color disparity between visible and invisible regions. To mitigate this, we incorporate a color consistency loss which measures the 

**==> picture [232 x 82] intentionally omitted <==**

## **3.3.3 Camera sampling during optimization** 

To optimize the 3D shape and texture using multi-view renderings, cameras are randomly sampled in a way that ensures comprehensive coverage of the entire body by adjusting various parameters. To mitigate the occurrence of mirrored appearance artifacts ( _i.e_ ., Janus-head), we incorporate view-aware prompts (“front/side/back/overhead view”) w.r.t. the viewing angle in the diffusion-based generation process, whose effectiveness has been demonstrated in DreamBooth [103]. To improve facial details, we also sample cameras positioned around the face, together with the additional prompt “face of” (see Appendix F). 

## **4. Experiments** 

We compare TeCH with state-of-the-art image-based 3D clothed human reconstruction methods, including bodyagnostic methods, such as PIFu [112], PIFuHD [113] and PHORHUM [5], as well as methods that utilize SMPL(X) [87, 101] body prior, such as PaMIR [151], ICON [131] and ECON [132]. For a fair comparison, all methods ( _i.e_ ., PIFu, PaMIR, ICON, ECON) utilize the same normal estimator from ICON. Official PIFu, PaMIR, and PHORHUM are used to evaluate the quality of texture. For ECON, we use ECONEX, due to its superior performance on both “OOD poses” and “OOD outfits” cases, as reported in the original paper [132]. Note that PHORHUM uses a different camera model which is incompatible with our testing data. Thus, we use PHORHUM only for qualitative comparisons. Implementation details of the network structure and optimization settings can be found in Appendix G. 

## **4.1. Models and Datasets** 

**Off-the-shelf models** . TeCH relies on multiple off-theshelf pre-trained models and does not need any additional training data. Specifically, we use the stablediffusion-v1.5 (runwayml) as T2I diffusion model, which is trained on LAION-5B, the VQA model BLIP [70] pretrained on 129M images from multiple datasets [15, 66, 81, 93, 96, 114] and fine-tuned on VQA2.0 [36], SegFormer[*] [127] pretrained from [10, 20, 23, 152] and fine- 

*matei-dorian/segformer-b5-finetuned-human-parsing 

1536 

Authorized licensed use limited to: Nazarbayev University. Downloaded on June 30,2026 at 07:49:14 UTC from IEEE Xplore.  Restrictions apply. 

|Method|3D Metrics<br>CAPE<br>THuman2.0<br>Chamfer _↓_<br>P2S _↓_<br>Normal _↓_<br>Chamfer _↓_<br>P2S _↓_<br>Normal _↓_|3D Metrics<br>CAPE<br>THuman2.0<br>Chamfer _↓_<br>P2S _↓_<br>Normal _↓_<br>Chamfer _↓_<br>P2S _↓_<br>Normal _↓_|3D Metrics<br>CAPE<br>THuman2.0<br>Chamfer _↓_<br>P2S _↓_<br>Normal _↓_<br>Chamfer _↓_<br>P2S _↓_<br>Normal _↓_|3D Metrics<br>CAPE<br>THuman2.0<br>Chamfer _↓_<br>P2S _↓_<br>Normal _↓_<br>Chamfer _↓_<br>P2S _↓_<br>Normal _↓_|3D Metrics<br>CAPE<br>THuman2.0<br>Chamfer _↓_<br>P2S _↓_<br>Normal _↓_<br>Chamfer _↓_<br>P2S _↓_<br>Normal _↓_|3D Metrics<br>CAPE<br>THuman2.0<br>Chamfer _↓_<br>P2S _↓_<br>Normal _↓_<br>Chamfer _↓_<br>P2S _↓_<br>Normal _↓_|2D Image Quality Metrics<br>CAPE<br>THuman2.0<br>PSNR_↑_<br>SSIM_↑_<br>LPIPS_↓_<br>PSNR_↑_<br>SSIM_↑_<br>LPIPS_↓_|2D Image Quality Metrics<br>CAPE<br>THuman2.0<br>PSNR_↑_<br>SSIM_↑_<br>LPIPS_↓_<br>PSNR_↑_<br>SSIM_↑_<br>LPIPS_↓_|2D Image Quality Metrics<br>CAPE<br>THuman2.0<br>PSNR_↑_<br>SSIM_↑_<br>LPIPS_↓_<br>PSNR_↑_<br>SSIM_↑_<br>LPIPS_↓_|
|---|---|---|---|---|---|---|---|---|---|
||||||w/o SMPL-X body prior|||||
|PIFu<br>PIFuHD||1.9683<br>1.6236<br>3.2018<br>2.9930|0.0623<br>0.0758||1.9305<br>1.8031<br>0.0802<br>2.4613<br>2.3605<br>0.0924||27.0994<br>0.9362<br>0.0987<br>-<br>-<br>-|23.5068<br>-|0.9296<br>0.1083<br>-<br>-|
||||||w/ SMPL-X body prior|||||
|PaMIR<br>ICON<br>ECON<br>TeCH (Ours)||1.3756<br>1.1852<br>0.8689<br>0.8397<br>0.9186<br>0.9227<br>**0.7416**<br>**0.6962**|0.0526<br>0.0360<br>0.0330<br>**0.0306**||1.2979<br>**1.1382**<br>1.2585<br>1.2364|**1.2188**<br>0.0676<br>1.2285<br>0.0623<br>1.4184<br>**0.0612**<br>1.2715<br>0.0642|27.7279<br>0.9456<br>0.0904<br>-<br>-<br>-<br>-<br>-<br>-<br>**28.3601**<br>**0.9490**<br>**0.0639**|22.5466<br>-<br>-<br>**25.2107**|0.9266<br>0.1082<br>-<br>-<br>-<br>-<br>**0.9363**<br>**0.0835**|



Table 1. **Quantitative evaluation against SOTAs.** TeCH surpasses SOTAs w.r.t. both 3D metrics (unit of Chamfer and P2S is _cm_ ) and 2D metrics. This demonstrates its superior performance in accurately reconstructing clothed human geometry with intricate details, as well as producing high-quality textures with consistent appearance. The best results are marked with “ **bold** ”, and the second-best with “underline”. 

tuned on ATR[75], PIXIE [26] trained on human images from multiple datasets [19, 81, 99, 125, 156], and the normal predictor of ICON [131] trained on AGORA [100]. 

**Datasets for evaluation** . Based on the high-fidelity 3D textured scans from CAPE [88] and THuman2.0 [138], we perform quantitative evaluations.We follow ICON [131] to analyze the robustness of reconstructions under both simple and complex poses (150 scans from CAPE). An additional 150 THuman2.0 scans are included, which comprise 100 subjects that were manually selected to represent a diverse range of clothing styles ( _e.g_ ., open jackets, long coats, garments with intricate patterns, _etc_ .), and 50 randomly sampled subjects. The images are rendered at a resolution of 512 _×_ 512. For qualitative comparison, we selected the SHHQ dataset [29] due to its wide range of textures, outfits, and gestures. From this dataset, we randomly sampled 90 images with official mask annotations. 

## **4.2. Quantitative Comparison** 

We quantitatively evaluate the quality of geometry and appearance, using the **Chamfer** (bidirectional point-tosurface) and **P2S** (1-directional point-to-surface) distance. Additionally, we report the L2 **Normal** error between normal images rendered from both meshes, to measure the consistency and fineness of local surface details, by rotating the camera by _{_ 0 _[◦] ,_ 90 _[◦] ,_ 180 _[◦] ,_ 270 _[◦] }_ w.r.t. to the input view. To evaluate the quality of the texture, we report 2D image quality metrics, on the multi-view colored images rendered in the same way as the normal images, including **PSNR** (Peak Signal-to-Noise Ratio), **SSIM** (Structural Similarity) and **LPIPS** (learned perceptual image path similarity). 

As shown in Tab. 1, TeCH demonstrates superior performance across all 2D metrics and 3D metrics on CAPE. This reveals that TeCH can accurately reconstruct both geometry and texture, even for subjects with challenging poses (CAPE) or loose clothing (THuman2.0). However, on THuman2.0, it achieves comparable reconstruction accuracy to prior-based methods. This can be attributed to the fact that the hallucinated back-side may differ from the ground truth while still appearing realistic. 

|Preference(%, _↑_)|PIFu PaMIR PHORHUM|ICON ECON|
|---|---|---|
|Geometry<br>Colored Rendering|88.6<br>87.0<br>81.7<br>95.1<br>93.7<br>93.0|97.94<br>90.48<br>-<br>-|



Table 2. **Perceptual study** . The percentages of user preference to TeCH compared to other baselines are reported. Most participants preferred TeCH in both geometry and colored rendering (texture). 

## **4.3. Perceptual Evaluation** 

We conducted a user study using 90 randomly sampled in-the-wild images from the SHHQ dataset [29]. Participants were shown videos showcasing rotating 3D humans reconstructed by TeCH, as well as the baselines (PaMIR [151], PIFu [112], ICON [131], ECON [132] and PHORHUM [5]). They were asked to choose the more realistic and consistent result based on the input image. We gathered a total of 3,150 pairwise comparisons from 63 participants, uniformly covering 90 SHHQ subjects. The results in Tab. 2 show that TeCH is preferred, both, in terms of geometry and texture. As illustrated in Fig. 7 and Appendix J, unlike other methods that reconstruct overly smooth surfaces and blurry textures, TeCH shows remarkable generalizability featuring diverse clothing styles and gestures, even for unseen regions. 

## **4.4. Ablation Studies** 

To assess the effectiveness of key designs in TeCH, we perform ablation studies on a 10% subset of the test set, consisting of 15 subjects from THuman2.0 and 15 from CAPE. The detailed analysis of these results is as follows: 

**Text guidance** . Figure 4 shows that VQA prompts help to recover the overall structure of clothing, while DreamBooth enhances the fine details of the texture pattern. Combining both text guidance sources yields the best results. This is also confirmed by the metrics in Table 3. A detailed analysis of individual descriptive texts ( _e.g_ ., garments, hairstyles, _etc_ .) is shown in Fig. 8 in the Appendix. 

**Geometric regularization** . As shown in Fig. 5, using only _L_[norm] SDS[to][optimize][the][geometry][will][produce][noisy][arti-] 

1537 

Authorized licensed use limited to: Nazarbayev University. Downloaded on June 30,2026 at 07:49:14 UTC from IEEE Xplore.  Restrictions apply. 

Figure 7. **Qualitative comparison on SHHQ images.** TeCH generalizes well on in-the-wild images with diverse clothing styles and textures. It successfully recovers the overall structure of the clothed body with text guidance, and generates realistic full-body texture which is consistent with the colored pattern and the material of the clothes. **Zoom in** to see the geometric details. 

|||Experiment settin|Experiment settin|eriment settings|||3D Metrics|3D Metrics||2D ImageQualityMetrics|2D ImageQualityMetrics|2D ImageQualityMetrics|
|---|---|---|---|---|---|---|---|---|---|---|---|---|
||VQA|DreamBooth|_L_norm|_L_CD|_M_A|multi-stage|Chamfer _↓_|P2S _↓_|Normal _↓_PSNR _↑_SSIM _↑_LPIPS _↓_||||
|Ours|||||||**0.9794**|0.9779|0.0466|26.7565|**0.9428**|**0.0741**|
||||||||0.9959|1.0192|**0.0454**|26.2078|0.9405|0.0813|
|A.|||||||1.0032|1.0218|0.0470|**26.9602**|**0.9428**|0.0785|
||||||||0.9957|0.9963|0.0468|26.0465|0.9395|0.0775|
|B.|||||||1.0882|**0.9203**|0.0870|-|-|-|
|C.|||||||-|-|-|26.6500|0.9427|0.0746|
||||||||-|-|-|26.6506|0.9425|0.0786|



Table 3. **Ablation study.** We quantitatively ablate each component. The best results are marked with “ **bold** ”, and the second-best with “underline”. All the factors are grouped w.r.t. to their influence: A. geometry+texture, B. geometry only, C. texture only. 

facts, particularity noticeable in loose clothes. The significant increase in “Normal” error shown in Tab. 3-B echos this. This issue can be mitigated by incorporating _L_ norm at the beginning of the optimization. 

**Consistent texture recovery** . The results presented in Fig. 6 demonstrate that _L_ CD notably enhances color consistency between the frontal and back sides, and ”multi-pose” training ( _M_ A) improves texture quality when dealing with self-occlusion scenarios. This improvement is further supported by Tab. 3-C, across all 2D image quality metrics. 

**Multi-stage optimization** . As shown in Tab. 3-A, compared to the decoupled two-stage optimization (Ours), the joint optimization results in a performance drop across both 3D and 2D metrics. This may be attributed to the entanglement of the gradients from the geometry and texture branches during optimization. Notably, in the separate texture stage, a colored image is rendered from the extracted mesh, saving 20% of the run time compared to joint optimization, which involves rendering from the DMTet mesh. 

## **5. Conclusion** 

TeCH reconstructs lifelike 3D clothed humans from a single images, with detailed geometry and consistent textures. The core insight is to leverage textual image description and DreamBooth to optimize the 3D avatar, including the invisible parts. Extensive experiments validate the superiority of TeCH over existing baselines w.r.t. geometry and rendering quality. We believe that this paradigm shift of diffusionguided reconstruction is a stepping stone for more general reconstruction tasks beyond human bodies. 

**Acknowledgments** . We thank H. Feng for the idea to ensure color consistency, V. Sklyarova for proofreading, H. Wang, H. Li, and X. Tang for their technical support, and C. Li, W. Liu and M. J. Black for their feedback. 

Y. Xiu is supported by the European Union’s Horizon 2020 research and innovation programme under the Marie SkłodowskaCurie grant agreement No.860768, H. Yi by the German Federal Ministry of Education and Research (BMBF): T¨ubingen AI Center, FKZ: 01IS18039B, Y. Huang and J. Tang by the National Natural Science Foundation of China (Grant NOs: 62273302, 62036009, 61936006, 61632003, 61375022, 61403005). 

1538 

Authorized licensed use limited to: Nazarbayev University. Downloaded on June 30,2026 at 07:49:14 UTC from IEEE Xplore.  Restrictions apply. 

## **References** 

- [1] Thiemo Alldieck, Marcus A. Magnor, Weipeng Xu, Christian Theobalt, and Gerard Pons-Moll. Detailed human avatars from monocular video. In _International Conference on 3D Vision (3DV)_ , 2018. 2 

- [2] Thiemo Alldieck, Marcus A. Magnor, Weipeng Xu, Christian Theobalt, and Gerard Pons-Moll. Video based reconstruction of 3D people models. In _Computer Vision and Pattern Recognition (CVPR)_ , 2018. 

- [3] Thiemo Alldieck, Marcus A. Magnor, Bharat Lal Bhatnagar, Christian Theobalt, and Gerard Pons-Moll. Learning to reconstruct people in clothing from a single RGB camera. In _Computer Vision and Pattern Recognition (CVPR)_ , 2019. 

- [4] Thiemo Alldieck, Gerard Pons-Moll, Christian Theobalt, and Marcus Magnor. Tex2Shape: Detailed Full Human Body Geometry From a Single Image. In _International Conference on Computer Vision (ICCV)_ , 2019. 2 

- [5] Thiemo Alldieck, Mihai Zanfir, and Cristian Sminchisescu. Photorealistic monocular 3d reconstruction of humans wearing clothing. In _Computer Vision and Pattern Recognition (CVPR)_ , 2022. 2, 6, 7, 12 

- [6] Rie Ando and Tong Zhang. Learning on graph with laplacian regularization. _Conference on Neural Information Processing Systems (NeurIPS)_ , 2006. 5 

- [7] Yogesh Balaji, Seungjun Nah, Xun Huang, Arash Vahdat, Jiaming Song, Qinsheng Zhang, Karsten Kreis, Miika Aittala, Timo Aila, Samuli Laine, Bryan Catanzaro, Tero Karras, and Ming-Yu Liu. eDiff-I: Text-to-Image Diffusion Models with Ensemble of Expert Denoisers. _arXiv preprint:2211.01324_ , 2022. 10 

- [8] Alexander Bergman, Petr Kellnhofer, Wang Yifan, Eric Chan, David Lindell, and Gordon Wetzstein. Generative neural articulated radiance fields. _Conference on Neural Information Processing Systems (NeurIPS)_ , 2022. 3 

- [9] Bharat Lal Bhatnagar, Garvita Tiwari, Christian Theobalt, and Gerard PonsMoll. Multi-Garment Net: Learning to dress 3D people from images. In _International Conference on Computer Vision (ICCV)_ , 2019. 2 

- [10] Holger Caesar, Jasper Uijlings, and Vittorio Ferrari. Coco-stuff: Thing and stuff classes in context. In _Computer Vision and Pattern Recognition (CVPR)_ , pages 1209–1218, 2018. 6 

- [11] Zhongang Cai, Daxuan Ren, Ailing Zeng, Zhengyu Lin, Tao Yu, Wenjia Wang, Xiangyu Fan, Yang Gao, Yifan Yu, Liang Pan, Fangzhou Hong, Mingyuan Zhang, Chen Change Loy, Lei Yang, and Ziwei Liu. HuMMan: Multi-modal 4d human dataset for versatile sensing and modeling. In _European Conference on Computer Vision (ECCV)_ , 2022. 3 

- [12] Yukang Cao, Guanying Chen, Kai Han, Wenqi Yang, and Kwan-Yee K. Wong. JIFF: Jointly-aligned Implicit Face Function for High Quality Single View Clothed Human Reconstruction. In _Computer Vision and Pattern Recognition (CVPR)_ , 2022. 2 

- [13] Yukang Cao, Yan-Pei Cao, Kai Han, Ying Shan, and Kwan-Yee K Wong. DreamAvatar: Text-and-Shape Guided 3D Human Avatar Generation via Diffusion Models. _arXiv preprint:2304.00916_ , 2023. 3 

- [14] Eric R. Chan, Koki Nagano, Matthew A. Chan, Alexander W. Bergman, Jeong Joon Park, Axel Levy, Miika Aittala, Shalini De Mello, Tero Karras, and Gordon Wetzstein. GeNVS: Generative novel view synthesis with 3D-aware diffusion models. In _International Conference on Computer Vision (ICCV)_ , 2023. 9 

- [15] Soravit Changpinyo, Piyush Sharma, Nan Ding, and Radu Soricut. Conceptual 12M: Pushing web-scale image-text pre-training to recognize long-tail visual concepts. In _Computer Vision and Pattern Recognition (CVPR)_ , 2021. 6 

- [16] Rui Chen, Yongwei Chen, Ningxin Jiao, and Kui Jia. Fantasia3D: Disentangling Geometry and Appearance for High-quality Text-to-3D Content Creation. In _International Conference on Computer Vision (ICCV)_ , 2023. 5 

- [17] Xu Chen, Tianjian Jiang, Jie Song, Jinlong Yang, Michael J Black, Andreas Geiger, and Otmar Hilliges. gDNA: Towards generative detailed neural avatars. In _Computer Vision and Pattern Recognition (CVPR)_ , 2022. 3 

- [18] Wei Cheng, Ruixiang Chen, Wanqi Yin, Siming Fan, Keyu Chen, Honglin He, Huiwen Luo, Zhongang Cai, Jingbo Wang, Yang Gao, Zhengming Yu, Zhengyu Lin, Daxuan Ren, Lei Yang, Ziwei Liu, Chen Change Loy, Chen Qian, Wayne Wu, Dahua Lin, Bo Dai, and Kwan-Yee Lin. DNA-Rendering: A Diverse Neural Actor Repository for High-Fidelity Human-centric Rendering. In _International Conference on Computer Vision (ICCV)_ , 2023. 3 

- [19] Vasileios Choutas, Georgios Pavlakos, Timo Bolkart, Dimitrios Tzionas, and Michael J. Black. Monocular expressive body regression through body-driven attention. In _European Conference on Computer Vision (ECCV)_ , pages 20–40, 2020. 7 

- [20] Marius Cordts, Mohamed Omran, Sebastian Ramos, Timo Scharw¨achter, Markus Enzweiler, Rodrigo Benenson, Uwe Franke, Stefan Roth, and Bernt Schiele. The cityscapes dataset. In _CVPR Workshop on the Future of Datasets in Vision_ . sn, 2015. 6 

- [21] Enric Corona, Mihai Zanfir, Thiemo Alldieck, Eduard Gabriel Bazavan, Andrei Zanfir, and Cristian Sminchisescu. Structured 3d features for reconstructing relightable and animatable avatars. In _Computer Vision and Pattern Recognition (CVPR)_ , 2023. 2 

- [22] Congyue Deng, Chiyu Jiang, Charles R Qi, Xinchen Yan, Yin Zhou, Leonidas Guibas, Dragomir Anguelov, et al. NeRDi: Single-View NeRF Synthesis with Language-Guided Diffusion as General Image Priors. In _Computer Vision and Pattern Recognition (CVPR)_ , 2023. 9 

- [23] Jia Deng, Wei Dong, Richard Socher, Li-Jia Li, Kai Li, and Li Fei-Fei. Imagenet: A large-scale hierarchical image database. In _Computer Vision and Pattern Recognition (CVPR)_ , pages 248–255. Ieee, 2009. 6 

- [24] Akio Doi and Akio Koide. An efficient method of triangulating equi-valued surfaces by using tetrahedral cells. _IEICE TRANSACTIONS on Information and Systems_ , 74(1):214–224, 1991. 4, 5, 9 

- [25] Zijian Dong, Xu Chen, Jinlong Yang, Michael J Black, Otmar Hilliges, and Andreas Geiger. AG3D: Learning to Generate 3D Avatars from 2D Image Collections. In _International Conference on Computer Vision (ICCV)_ , 2023. 3 

- [26] Yao Feng, Vasileios Choutas, Timo Bolkart, Dimitrios Tzionas, and Michael J. Black. Collaborative regression of expressive bodies using moderation. In _International Conference on 3D Vision (3DV)_ , pages 792–804, 2021. 2, 4, 7, 12 

- [27] Yao Feng, Jinlong Yang, Marc Pollefeys, Michael J. Black, and Timo Bolkart. Capturing and animation of body and clothing from monocular video. In _SIGGRAPH Asia 2022 Conference Papers_ , 2022. 12 

- [28] Yao Feng, Weiyang Liu, Timo Bolkart, Jinlong Yang, Marc Pollefeys, and Michael J. Black. Learning Disentangled Avatars with Hybrid 3D Representations. _arXiv_ , 2023. 12 

- [29] Jianglin Fu, Shikai Li, Yuming Jiang, Kwan-Yee Lin, Chen Qian, ChenChange Loy, Wayne Wu, and Ziwei Liu. StyleGAN-Human: A Data-Centric Odyssey of Human Generation. _European Conference on Computer Vision (ECCV)_ , 2022. 3, 7, 12 

- [30] Valentin Gabeur, Jean-S´ebastien Franco, Xavier Martin, Cordelia Schmid, and Gregory Rogez. Moulding humans: Non-parametric 3D human shape estimation from single images. In _International Conference on Computer Vision (ICCV)_ , 2019. 2 

- [31] Rinon Gal, Yuval Alaluf, Yuval Atzmon, Or Patashnik, Amit H Bermano, Gal Chechik, and Daniel Cohen-Or. An image is worth one word: Personalizing text-to-image generation using textual inversion. In _International Conference on Learning Representations (ICLR)_ , 2023. 9 

- [32] Daiheng Gao, Yuliang Xiu, Kailin Li, Lixin Yang, Feng Wang, Peng Zhang, Bang Zhang, Cewu Lu, and Ping Tan. DART: Articulated Hand Model with Diverse Accessories and Rich Textures. In _Thirty-sixth Conference on Neural Information Processing Systems Datasets and Benchmarks Track_ , 2022. 12 

- [33] Jun Gao, Wenzheng Chen, Tommy Xiang, Alec Jacobson, Morgan McGuire, and Sanja Fidler. Learning deformable tetrahedral meshes for 3d reconstruction. _Conference on Neural Information Processing Systems (NeurIPS)_ , 33: 9936–9947, 2020. 2, 4, 9 

- [34] Jun Gao, Tianchang Shen, Zian Wang, Wenzheng Chen, Kangxue Yin, Daiqing Li, Or Litany, Zan Gojcic, and Sanja Fidler. GET3D: A Generative Model of High Quality 3D Textured Shapes Learned from Images. In _Conference on Neural Information Processing Systems (NeurIPS)_ , 2022. 3 

- [35] Yuying Ge, Ruimao Zhang, Lingyun Wu, Xiaogang Wang, Xiaoou Tang, and Ping Luo. A versatile benchmark for detection, pose estimation, segmentation and re-identification of clothing images. In _Computer Vision and Pattern Recognition (CVPR)_ , 2019. 3 

- [36] Yash Goyal, Tejas Khot, Douglas Summers-Stay, Dhruv Batra, and Devi Parikh. Making the V in VQA matter: Elevating the role of image understanding in Visual Question Answering. In _Conference on Computer Vision and Pattern Recognition (CVPR)_ , 2017. 6 

- [37] Artur Grigorev, Karim Iskakov, Anastasia Ianina, Renat Bashirov, Ilya Zakharkin, Alexander Vakhitov, and Victor Lempitsky. Stylepeople: A generative model of fullbody human avatars. In _Computer Vision and Pattern Recognition (CVPR)_ , pages 5151–5160, 2021. 3 

- [38] Si Hang. Tetgen, a delaunay-based quality tetrahedral mesh generator. _ACM Trans. Math. Softw_ , 41(2):11, 2015. 10 

- [39] Tong He, John P. Collomosse, Hailin Jin, and Stefano Soatto. Geo-PIFu: Geometry and pixel aligned implicit functions for single-view human reconstruction. In _Conference on Neural Information Processing Systems (NeurIPS)_ , 2020. 2 

- [40] Tong He, Yuanlu Xu, Shunsuke Saito, Stefano Soatto, and Tony Tung. ARCH++: Animation-Ready Clothed Human Reconstruction Revisited. In _International Conference on Computer Vision (ICCV)_ , pages 11046–11056, 2021. 2 

- [41] Fangzhou Hong, Mingyuan Zhang, Liang Pan, Zhongang Cai, Lei Yang, and Ziwei Liu. Avatarclip: Zero-shot text-driven generation and animation of 3d avatars. _Transactions on Graphics (TOG)_ , 2022. 3 

- [42] Fangzhou Hong, Zhaoxi Chen, Yushi Lan, Liang Pan, and Ziwei Liu. EVA3D: Compositional 3D Human Generation from 2D Image Collections. In _International Conference on Learning Representations (ICLR)_ , 2023. 3 

1539 

Authorized licensed use limited to: Nazarbayev University. Downloaded on June 30,2026 at 07:49:14 UTC from IEEE Xplore.  Restrictions apply. 

- [43] Hugues Hoppe. New quadric metric for simplifying meshes with appearance attributes. In _Proceedings Visualization’99 (Cat. No. 99CB37067)_ , pages 59– 510. IEEE, 1999. 10 

- [44] Edward J Hu, Yelong Shen, Phillip Wallis, Zeyuan Allen-Zhu, Yuanzhi Li, Shean Wang, Lu Wang, and Weizhu Chen. Lora: Low-rank adaptation of large language models. _arXiv preprint arXiv:2106.09685_ , 2021. 12 

- [45] Shoukang Hu, Fangzhou Hong, Liang Pan, Haiyi Mei, Lei Yang, and Ziwei Liu. Sherf: Generalizable human nerf from a single image. In _International Conference on Computer Vision (ICCV)_ , 2023. 3 

- [46] Yukun Huang, Jianan Wang, Ailing Zeng, He Cao, Xianbiao Qi, Yukai Shi, Zheng-Jun Zha, and Lei Zhang. DreamWaltz: Make a Scene with Complex 3D Animatable Avatars. In _Conference on Neural Information Processing Systems (NeurIPS)_ , 2023. 3 

- [47] Yangyi Huang, Hongwei Yi, Weiyang Liu, Haofan Wang, Boxi Wu, Wenxiao Wang, Binbin Lin, Debing Zhang, and Deng Cai. One-shot implicit animatable avatars with model-based priors. In _International Conference on Computer Vision (ICCV)_ , 2023. 3 

- [48] Zeng Huang, Yuanlu Xu, Christoph Lassner, Hao Li, and Tony Tung. ARCH: Animatable Reconstruction of Clothed Humans. In _Computer Vision and Pattern Recognition (CVPR)_ , pages 3093–3102, 2020. 2 

- [49] Mustafa Is¸ık, Martin R¨unz, Markos Georgopoulos, Taras Khakhulin, Jonathan Starck, Lourdes Agapito, and Matthias Nießner. HumanRF: High-Fidelity Neural Radiance Fields for Humans in Motion. _Transactions on Graphics (TOG)_ , 2023. 3 

- [50] Ajay Jain, Matthew Tancik, and Pieter Abbeel. Putting NeRF on a Diet: Semantically Consistent Few-Shot View Synthesis. In _International Conference on Computer Vision (ICCV)_ , pages 5885–5894, 2021. 9 

- [51] Boyi Jiang, Juyong Zhang, Yang Hong, Jinhao Luo, Ligang Liu, and Hujun Bao. BCNet: Learning body and cloth shape from a single image. In _European Conference on Computer Vision (ECCV)_ , 2020. 2 

- [52] Ruixiang Jiang, Can Wang, Jingbo Zhang, Menglei Chai, Mingming He, Dongdong Chen, and Jing Liao. Avatarcraft: Transforming text into neural human avatars with parameterized shape and pose control. In _International Conference on Computer Vision (ICCV)_ , 2023. 3 

- [53] Hanbyul Joo, Tomas Simon, and Yaser Sheikh. Total capture: A 3d deformation model for tracking faces, hands, and bodies. In _Computer Vision and Pattern Recognition (CVPR)_ , 2018. 2, 3 

- [54] Xuan Ju, Ailing Zeng, Chenchen Zhao, Jianan Wang, Lei Zhang, and Qiang Xu. HumanSD: A Native Skeleton-Guided Diffusion Model for Human Image Generation. In _International Conference on Computer Vision (ICCV)_ , 2023. 12 

- [55] Angjoo Kanazawa, Michael J. Black, David W. Jacobs, and Jitendra Malik. End-to-end recovery of human shape and pose. In _Computer Vision and Pattern Recognition (CVPR)_ , pages 7122–7131, 2018. 2 

- [56] Tero Karras, Samuli Laine, Miika Aittala, Janne Hellsten, Jaakko Lehtinen, and Timo Aila. Analyzing and improving the image quality of StyleGAN. In _Computer Vision and Pattern Recognition (CVPR)_ , 2020. 3 

- [57] Bernhard Kerbl, Georgios Kopanas, Thomas Leimk¨uhler, and George Drettakis. 3d gaussian splatting for real-time radiance field rendering. _Transactions on Graphics (TOG)_ , 42(4), 2023. 12 

- [58] Byungjun Kim, Patrick Kwon, Kwangho Lee, Myunggi Lee, Sookwan Han, Daesik Kim, and Hanbyul Joo. Chupa: Carving 3D Clothed Humans from Skinned Shape Priors using 2D Diffusion Probabilistic Models. In _International Conference on Computer Vision (ICCV)_ , 2023. 3 

- [59] Taeksoo Kim, Shunsuke Saito, and Hanbyul Joo. NCHO: Unsupervised Learning for Neural 3D Composition of Humans and Objects. In _International Conference on Computer Vision (ICCV)_ , 2023. 12 

- [60] Taeksoo Kim, Byungjun Kim, Shunsuke Saito, and Hanbyul Joo. GALA: Generating Animatable Layered Assets from a Single Scan, 2024. 12 

- [61] Muhammed Kocabas, Nikos Athanasiou, and Michael J. Black. VIBE: Video inference for human body pose and shape estimation. In _Computer Vision and Pattern Recognition (CVPR)_ , pages 5252–5262, 2020. 2 

- [62] Muhammed Kocabas, Chun-Hao P. Huang, Otmar Hilliges, and Michael J. Black. PARE: Part attention regressor for 3D human body estimation. In _International Conference on Computer Vision (ICCV)_ , pages 11127–11137, 2021. 

- [63] Muhammed Kocabas, Chun-Hao P. Huang, Joachim Tesch, Lea M¨uller, Otmar Hilliges, and Michael J. Black. SPEC: Seeing people in the wild with an estimated camera. In _International Conference on Computer Vision (ICCV)_ , pages 11035–11045, 2021. 

- [64] Nikos Kolotouros, Georgios Pavlakos, Michael J. Black, and Kostas Daniilidis. Learning to reconstruct 3D human pose and shape via model-fitting in the loop. In _International Conference on Computer Vision (ICCV)_ , pages 2252–2261, 2019. 2 

- [65] Nikos Kolotouros, Thiemo Alldieck, Andrei Zanfir, Eduard Gabriel Bazavan, Mihai Fieraru, and Cristian Sminchisescu. DreamHuman: Animatable 3D Avatars from Text. In _Conference on Neural Information Processing Systems (NeurIPS)_ , 2023. 3 

- [66] Ranjay Krishna, Yuke Zhu, Oliver Groth, Justin Johnson, Kenji Hata, Joshua Kravitz, Stephanie Chen, Yannis Kalantidis, Li-Jia Li, David A Shamma, et al. Visual genome: Connecting language and vision using crowdsourced dense image annotations. _International Journal of Computer Vision (IJCV)_ , 123: 32–73, 2017. 6 

- [67] Samuli Laine, Janne Hellsten, Tero Karras, Yeongho Seol, Jaakko Lehtinen, and Timo Aila. Modular primitives for high-performance differentiable rendering. _Transactions on Graphics (TOG)_ , 39(6), 2020. 4, 10 

- [68] Verica Lazova, Eldar Insafutdinov, and Gerard Pons-Moll. 360-Degree textures of people in clothing from a single image. In _International Conference on 3D Vision (3DV)_ , 2019. 2 

- [69] Jiefeng Li, Chao Xu, Zhicun Chen, Siyuan Bian, Lixin Yang, and Cewu Lu. HybrIK: A hybrid analytical-neural inverse kinematics solution for 3D human pose and shape estimation. In _Computer Vision and Pattern Recognition (CVPR)_ , pages 3383–3393, 2021. 2 

- [70] Junnan Li, Dongxu Li, Caiming Xiong, and Steven Hoi. Blip: Bootstrapping language-image pre-training for unified vision-language understanding and generation. In _International Conference on Machine Learning (ICML)_ , pages 12888–12900. PMLR, 2022. 2, 3, 4, 6, 10 

- [71] Jiefeng Li, Siyuan Bian, Qi Liu, Jiasheng Tang, Fan Wang, and Cewu Lu. NIKI: Neural inverse kinematics with invertible neural networks for 3d human pose and shape estimation. In _Computer Vision and Pattern Recognition (CVPR)_ , 2023. 2 

- [72] Ruilong Li, Kyle Olszewski, Yuliang Xiu, Shunsuke Saito, Zeng Huang, and Hao Li. Volumetric human teleportation. In _ACM SIGGRAPH 2020 Real-Time Live_ , 2020. 2 

- [73] Ren Li, Benoˆıt Guillard, and Pascal Fua. Isp: Multi-layered garment draping with implicit sewing patterns. In _Conference on Neural Information Processing Systems (NeurIPS)_ , 2023. 12 

- [74] Zhihao Li, Jianzhuang Liu, Zhensong Zhang, Songcen Xu, and Youliang Yan. CLIFF: Carrying Location Information in Full Frames into Human Pose and Shape Estimation. In _European Conference on Computer Vision (ECCV)_ , pages 590–606. Springer, 2022. 2 

- [75] Xiaodan Liang, Si Liu, Xiaohui Shen, Jianchao Yang, Luoqi Liu, Jian Dong, Liang Lin, and Shuicheng Yan. Deep human parsing with active template regression. _Transactions on Pattern Analysis and Machine Intelligence (TPAMI)_ , 37(12):2402–2414, 2015. 7 

- [76] Xiaodan Liang, Si Liu, Xiaohui Shen, Jianchao Yang, Luoqi Liu, Jian Dong, Liang Lin, and Shuicheng Yan. Deep human parsing with active template regression. _Transactions on Pattern Analysis and Machine Intelligence (TPAMI)_ , 37(12):2402–2414, 2015. 4 

- [77] Xiaodan Liang, Chunyan Xu, Xiaohui Shen, Jianchao Yang, Si Liu, Jinhui Tang, Liang Lin, and Shuicheng Yan. Human parsing with contextualized convolutional neural network. In _International Conference on Computer Vision (ICCV)_ , pages 1386–1394, 2015. 4 

- [78] Tingting Liao, Xiaomei Zhang, Yuliang Xiu, Hongwei Yi, Xudong Liu, GuoJun Qi, Yong Zhang, Xuan Wang, Xiangyu Zhu, and Zhen Lei. High-Fidelity Clothed Avatar Reconstruction from a Single Image. In _Computer Vision and Pattern Recognition (CVPR)_ , 2023. 2 

- [79] Tingting Liao, Hongwei Yi, Yuliang Xiu, Jiaxiang Tang, Yangyi Huang, Justus Thies, and Michael J. Black. TADA! Text to Animatable Digital Avatars. In _International Conference on 3D Vision (3DV)_ , 2024. 3 

- [80] Chen-Hsuan Lin, Jun Gao, Luming Tang, Towaki Takikawa, Xiaohui Zeng, Xun Huang, Karsten Kreis, Sanja Fidler, Ming-Yu Liu, and Tsung-Yi Lin. Magic3D: High-Resolution Text-to-3D Content Creation. In _Computer Vision and Pattern Recognition (CVPR)_ , 2023. 9 

- [81] Tsung-Yi Lin, Michael Maire, Serge Belongie, James Hays, Pietro Perona, Deva Ramanan, Piotr Doll´ar, and C Lawrence Zitnick. Microsoft COCO: common objects in context. In _European Conference on Computer Vision (ECCV)_ , pages 740–755, 2014. 6, 7 

- [82] Minghua Liu, Chao Xu, Haian Jin, Linghao Chen, Mukund T, Zexiang Xu, and Hao Su. One-2-3-45: Any Single Image to 3D Mesh in 45 Seconds without Per-Shape Optimization. _arXiv preprint_ , 2023. 9 

- [83] Ruoshi Liu, Rundi Wu, Basile Van Hoorick, Pavel Tokmakov, Sergey Zakharov, and Carl Vondrick. Zero-1-to-3: Zero-shot One Image to 3D Object. In _International Conference on Computer Vision (ICCV)_ , 2023. 9 

- [84] Weiyang Liu, Zeju Qiu, Yao Feng, Yuliang Xiu, Yuxuan Xue, Longhui Yu, Haiwen Feng, Zhen Liu, Juyeon Heo, Songyou Peng, Yandong Wen, Michael J. Black, Adrian Weller, and Bernhard Sch¨olkopf. ParameterEfficient Orthogonal Finetuning via Butterfly Factorization. In _International Conference on Learning Representations (ICLR)_ , 2024. 12 

- [85] Ziwei Liu, Ping Luo, Shi Qiu, Xiaogang Wang, and Xiaoou Tang. Deepfashion: Powering robust clothes recognition and retrieval with rich annotations. In _Proceedings of IEEE Conference on Computer Vision and Pattern Recognition (CVPR)_ , 2016. 3 

- [86] Zhen Liu, Yao Feng, Yuliang Xiu, Weiyang Liu, Liam Paull, Michael J. Black, and Bernhard Sch¨olkopf. Ghost on The Shell: An Expressive Representation of General 3D Shapes. In _International Conference on Learning Representations (ICLR)_ , 2024. 12 

1540 

Authorized licensed use limited to: Nazarbayev University. Downloaded on June 30,2026 at 07:49:14 UTC from IEEE Xplore.  Restrictions apply. 

- [87] Matthew Loper, Naureen Mahmood, Javier Romero, Gerard Pons-Moll, and Michael J. Black. SMPL: A skinned multi-person linear model. _Transactions on Graphics (TOG)_ , 34(6):248:1–248:16, 2015. 2, 3, 6 

- [88] Qianli Ma, Jinlong Yang, Anurag Ranjan, Sergi Pujades, Gerard Pons-Moll, Siyu Tang, and Michael J. Black. Learning to Dress 3D People in Generative Clothing. In _Computer Vision and Pattern Recognition (CVPR)_ , 2020. 3, 7 

- [89] Naureen Mahmood, Nima Ghorbani, Nikolaus F. Troje, Gerard Pons-Moll, and Michael J. Black. AMASS: Archive of Motion Capture as Surface Shapes. In _International Conference on Computer Vision (ICCV)_ , pages 5442–5451, 2019. 12 

- [90] Luke Melas-Kyriazi, Christian Rupprecht, Iro Laina, and Andrea Vedaldi. RealFusion: 360 Reconstruction of Any Object from a Single Image. In _Computer Vision and Pattern Recognition (CVPR)_ , 2023. 9 

- [91] Chong Mou, Xintao Wang, Liangbin Xie, Jian Zhang, Zhongang Qi, Ying Shan, and Xiaohu Qie. T2i-adapter: Learning adapters to dig out more controllable ability for text-to-image diffusion models. _arXiv preprint:2302.08453_ , 2023. 12 

- [92] Thomas M¨uller, Alex Evans, Christoph Schied, and Alexander Keller. Instant neural graphics primitives with a multiresolution hash encoding. _ACM Transactions on Graphics (ToG)_ , 41(4):1–15, 2022. 4 

- [93] Edwin G. Ng, Bo Pang, Piyush Kumar Sharma, and Radu Soricut. Understanding guided image captioning performance across domains. In _Conference on Computational Natural Language Learning_ , 2020. 6 

- [94] Atsuhiro Noguchi, Xiao Sun, Stephen Lin, and Tatsuya Harada. Unsupervised learning of efficient geometry-aware neural articulated representations. In _European Conference on Computer Vision (ECCV)_ , pages 597–614. Springer, 2022. 3 

- [95] Hayato Onizuka, Zehra Haiyrci, Diego Thomas, Akihiro Sugimoto, Hideaki Uchiyama, and Rin-Ichiro Taniguchi. TetraTSDF: 3D human reconstruction from a single image with a tetrahedral outer shell. In _Computer Vision and Pattern Recognition (CVPR)_ , 2020. 4 

- [96] Vicente Ordonez, Girish Kulkarni, and Tamara Berg. Im2text: Describing images using 1 million captioned photographs. In _Conference on Neural Information Processing Systems (NeurIPS)_ , 2011. 6 

- [97] Pablo Palafox, Aljaˇz Boˇziˇc, Justus Thies, Matthias Nießner, and Angela Dai. NPMs: Neural Parametric Models for 3D Deformable Shapes. In _International Conference on Computer Vision (ICCV)_ , 2021. 3 

- [98] Pablo Palafox, Nikolaos Sarafianos, Tony Tung, and Angela Dai. Spams: Structured implicit parametric models. _Computer Vision and Pattern Recognition (CVPR)_ , 2022. 3 

- [99] Omkar M. Parkhi, Andrea Vedaldi, and Andrew Zisserman. Deep face recognition. In _British Machine Vision Conference (BMVC)_ , 2015. 7 

- [100] Priyanka Patel, Chun-Hao Paul Huang, Joachim Tesch, David Hoffmann, Shashank Tripathi, and Michael J. Black. AGORA: Avatars in geography optimized for regression analysis. In _Computer Vision and Pattern Recognition (CVPR)_ , pages 13468–13478, 2021. 7 

- [101] Georgios Pavlakos, Vasileios Choutas, Nima Ghorbani, Timo Bolkart, Ahmed AA Osman, Dimitrios Tzionas, and Michael J Black. Expressive body capture: 3d hands, face, and body from a single image. In _Computer Vision and Pattern Recognition (CVPR)_ , pages 10975–10985, 2019. 2, 3, 6 

- [102] Gerard Pons-Moll, Sergi Pujades, Sonny Hu, and Michael Black. ClothCap: Seamless 4D Clothing Capture and Retargeting. _International Conference on Computer Graphics and Interactive Techniques (SIGGRAPH)_ , 36(4), 2017. Two first authors contributed equally. 2 

- [103] Ben Poole, Ajay Jain, Jonathan T Barron, and Ben Mildenhall. DreamFusion: Text-to-3d using 2d diffusion. In _International Conference on Learning Representations (ICLR)_ , 2023. 2, 3, 5, 6, 9, 10 

- [104] Guocheng Qian, Jinjie Mai, Abdullah Hamdi, Jian Ren, Aliaksandr Siarohin, Bing Li, Hsin-Ying Lee, Ivan Skorokhodov, Peter Wonka, Sergey Tulyakov, et al. Magic123: One Image to High-Quality 3D Object Generation Using Both 2D and 3D Diffusion Priors. In _International Conference on Learning Representations (ICLR)_ , 2024. 9 

- [105] Zeju Qiu, Weiyang Liu, Haiwen Feng, Yuxuan Xue, Yao Feng, Zhen Liu, Dan Zhang, Adrian Weller, and Bernhard Sch¨olkopf. Controlling Text-to-Image Diffusion by Orthogonal Finetuning. In _Conference on Neural Information Processing Systems (NeurIPS)_ , 2023. 12 

- [106] Alec Radford, Jong Wook Kim, Chris Hallacy, Aditya Ramesh, Gabriel Goh, Sandhini Agarwal, Girish Sastry, Amanda Askell, Pamela Mishkin, Jack Clark, Gretchen Krueger, and Ilya Sutskever. Learning Transferable Visual Models From Natural Language Supervision. In _International Conference on Machine Learning (ICML)_ , pages 8748–8763. PMLR, 2021. 3, 9 

- [107] Amit Raj, Srinivas Kaza, Ben Poole, Michael Niemeyer, Ben Mildenhall, Nataniel Ruiz, Shiran Zada, Kfir Aberman, Michael Rubenstein, Jonathan Barron, Yuanzhen Li, and Varun Jampani. DreamBooth3D: Subject-Driven Text-to-3D Generation. In _International Conference on Computer Vision (ICCV)_ , 2023. 9 

- [108] Aditya Ramesh, Mikhail Pavlov, Gabriel Goh, Scott Gray, Chelsea Voss, Alec Radford, Mark Chen, and Ilya Sutskever. Zero-Shot Text-to-Image Generation. In _International Conference on Machine Learning (ICML)_ , 2021. 9 

- [109] Robin Rombach, Andreas Blattmann, Dominik Lorenz, Patrick Esser, and Bj¨orn Ommer. High-resolution image synthesis with latent diffusion models. In _Computer Vision and Pattern Recognition (CVPR)_ , pages 10684–10695, 2022. 9, 10 

- [110] Nataniel Ruiz, Yuanzhen Li, Varun Jampani, Yael Pritch, Michael Rubinstein, and Kfir Aberman. DreamBooth: Fine tuning text-to-image diffusion models for subject-driven generation. In _Computer Vision and Pattern Recognition (CVPR)_ , 2023. 2, 3, 4, 9 

- [111] Chitwan Saharia, William Chan, Saurabh Saxena, Lala Li, Jay Whang, Emily Denton, Seyed Kamyar Seyed Ghasemipour, Burcu Karagol Ayan, S Sara Mahdavi, Rapha Gontijo Lopes, et al. Photorealistic text-to-image diffusion models with deep language understanding. In _Conference on Neural Information Processing Systems (NeurIPS)_ , 2022. 2, 9 

- [112] Shunsuke Saito, Zeng Huang, Ryota Natsume, Shigeo Morishima, Hao Li, and Angjoo Kanazawa. PIFu: Pixel-aligned implicit function for high-resolution clothed human digitization. In _International Conference on Computer Vision (ICCV)_ , pages 2304–2314, 2019. 2, 6, 7, 12 

- [113] Shunsuke Saito, Tomas Simon, Jason Saragih, and Hanbyul Joo. PIFuHD: Multi-Level Pixel-Aligned Implicit Function for High-Resolution 3D Human Digitization. In _Computer Vision and Pattern Recognition (CVPR)_ , pages 81– 90, 2020. 2, 6, 12 

- [114] Christoph Schuhmann, Romain Beaumont, Richard Vencu, Cade W Gordon, Ross Wightman, Mehdi Cherti, Theo Coombes, Aarush Katta, Clayton Mullis, Mitchell Wortsman, Patrick Schramowski, Srivatsa R Kundurthy, Katherine Crowson, Ludwig Schmidt, Robert Kaczmarczyk, and Jenia Jitsev. LAION5B: An open large-scale dataset for training next generation image-text models. In _Thirty-sixth Conference on Neural Information Processing Systems Datasets and Benchmarks Track_ , 2022. 3, 6 

- [115] Tianchang Shen, Jun Gao, Kangxue Yin, Ming-Yu Liu, and Sanja Fidler. Deep marching tetrahedra: a hybrid representation for high-resolution 3d shape synthesis. _Conference on Neural Information Processing Systems (NeurIPS)_ , 34: 6087–6101, 2021. 2, 4, 9 

- [116] Tianchang Shen, Jacob Munkberg, Jon Hasselgren, Kangxue Yin, Zian Wang, Wenzheng Chen, Zan Gojcic, Sanja Fidler, Nicholas Sharp, and Jun Gao. Flexible Isosurface Extraction for Gradient-Based Mesh Optimization. _Transactions on Graphics (TOG)_ , 42(4), 2023. 12 

- [117] Vanessa Sklyarova, Jenya Chelishev, Andreea Dogaru, Igor Medvedev, Victor Lempitsky, and Egor Zakharov. Neural Haircut: Prior-Guided StrandBased Hair Reconstruction. In _International Conference on Computer Vision (ICCV)_ , 2023. 12 

- [118] David Smith, Matthew Loper, Xiaochen Hu, Paris Mavroidis, and Javier Romero. FACSIMILE: Fast and accurate scans from an image in less than a second. In _International Conference on Computer Vision (ICCV)_ , 2019. 2 

- [119] Jiang Suyi, Jiang Haoran, Wang Ziyu, Luo Haimin, Chen Wenzheng, and Xu Lan. HumanGen: Generating Human Radiance Fields with Explicit Priors. In _Computer Vision and Pattern Recognition (CVPR)_ , 2023. 3 

- [120] David Svitov, Dmitrii Gudkov, Renat Bashirov, and Victor Lemptisky. Dinar: Diffusion inpainting of neural textures for one-shot human avatars. In _International Conference on Computer Vision (ICCV)_ , 2023. 3 

- [121] Junshu Tang, Tengfei Wang, Bo Zhang, Ting Zhang, Ran Yi, Lizhuang Ma, and Dong Chen. Make-It-3D: High-Fidelity 3D Creation from A Single Image with Diffusion Prior. In _International Conference on Computer Vision (ICCV)_ , 2023. 9 

- [122] Haochen Wang, Xiaodan Du, Jiahao Li, Raymond A Yeh, and Greg Shakhnarovich. Score Jacobian Chaining: Lifting Pretrained 2D Diffusion Models for 3D Generation. In _Computer Vision and Pattern Recognition (CVPR)_ , 2023. 9 

- [123] Tengfei Wang, Bo Zhang, Ting Zhang, Shuyang Gu, Jianmin Bao, Tadas Baltrusaitis, Jingjing Shen, Dong Chen, Fang Wen, Qifeng Chen, et al. Rodin: A Generative Model for Sculpting 3D Digital Avatars Using Diffusion. In _Computer Vision and Pattern Recognition (CVPR)_ , 2023. 3 

- [124] Daniel Watson, William Chan, Ricardo Martin-Brualla, Jonathan Ho, Andrea Tagliasacchi, and Mohammad Norouzi. Novel View Synthesis with Diffusion Models (3DiM). In _International Conference on Learning Representations (ICLR)_ , 2023. 9 

- [125] Donglai Xiang, Hanbyul Joo, and Yaser Sheikh. Monocular total capture: Posing face, body, and hands in the wild. In _Computer Vision and Pattern Recognition (CVPR)_ , pages 10957–10966, 2019. 7 

- [126] Donglai Xiang, Fabian Prada, Chenglei Wu, and Jessica K. Hodgins. MonoClothCap: Towards temporally coherent clothing capture from monocular RGB video. In _International Conference on 3D Vision (3DV)_ , 2020. 2 

- [127] Enze Xie, Wenhai Wang, Zhiding Yu, Anima Anandkumar, Jose M Alvarez, and Ping Luo. SegFormer: Simple and efficient design for semantic segmentation with transformers. _Conference on Neural Information Processing Systems (NeurIPS)_ , 34:12077–12090, 2021. 2, 3, 4, 6, 10 

1541 

Authorized licensed use limited to: Nazarbayev University. Downloaded on June 30,2026 at 07:49:14 UTC from IEEE Xplore.  Restrictions apply. 

- [128] Zhangyang Xiong, Di Kang, Derong Jin, Weikai Chen, Linchao Bao, and Xiaoguang Han. Get3DHuman: Lifting StyleGAN-Human into a 3D Generative Model using Pixel-aligned Reconstruction Priors. In _International Conference on Computer Vision (ICCV)_ , 2023. 3 

- [129] Zhangyang Xiong, Chenghong Li, Kenkun Liu, Hongjie Liao, Jianqiao Hu, Junyi Zhu, Shuliang Ning, Lingteng Qiu, Chongjie Wang, Shijie Wang, et al. MVHumanNet: A Large-scale Dataset of Multi-view Daily Dressing Human Captures. _arXiv preprint arXiv:2312.02963_ , 2023. 3 

- [130] Yuliang Xiu, Ruilong Li, Shunsuke Saito, Zeng Huang, Kyle Olszewski, and Hao Li. Monocular real-time volumetric performance capture. In _European Conference on Computer Vision (ECCV)_ , pages 49–67, 2020. 2 

- [131] Yuliang Xiu, Jinlong Yang, Dimitrios Tzionas, and Michael J. Black. ICON: Implicit Clothed humans Obtained from Normals. In _Computer Vision and Pattern Recognition (CVPR)_ , 2022. 2, 5, 6, 7, 12 

- [132] Yuliang Xiu, Jinlong Yang, Xu Cao, Dimitrios Tzionas, and Michael J. Black. ECON: Explicit Clothed humans Optimized via Normal integration. In _Computer Vision and Pattern Recognition (CVPR)_ , 2023. 2, 5, 6, 7, 12 

- [133] Dejia Xu, Yifan Jiang, Peihao Wang, Zhiwen Fan, Yi Wang, and Zhangyang Wang. NeuralLift-360: Lifting An In-the-wild 2D Photo to A 3D Object with 360° Views. _Computer Vision and Pattern Recognition (CVPR)_ , 2023. 9 

- [134] Hongyi Xu, Eduard Gabriel Bazavan, Andrei Zanfir, William T. Freeman, Rahul Sukthankar, and Cristian Sminchisescu. GHUM & GHUML: Generative 3D human shape and articulated pose models. In _Computer Vision and Pattern Recognition (CVPR)_ , pages 6183–6192, 2020. 2, 3 

- [135] Yuxuan Xue, Bharat Lal Bhatnagar, Riccardo Marin, Nikolaos Sarafianos, Yuanlu Xu, Gerard Pons-Moll, and Tony Tung. NSF: Neural Surface Fields for Human Modeling from Monocular Depth. In _International Conference on Computer Vision (ICCV)_ , 2023. 3 

   - [150] Zerong Zheng, Tao Yu, Yixuan Wei, Qionghai Dai, and Yebin Liu. DeepHuman: 3D Human Reconstruction From a Single Image. In _International Conference on Computer Vision (ICCV)_ , pages 7738–7748, 2019. 3 

   - [151] Zerong Zheng, Tao Yu, Yebin Liu, and Qionghai Dai. PaMIR: Parametric Model-conditioned Implicit Representation for image-based human reconstruction. _Transactions on Pattern Analysis and Machine Intelligence (TPAMI)_ , 44(6):3170–3184, 2021. 2, 6, 7, 12 

   - [152] Bolei Zhou, Hang Zhao, Xavier Puig, Sanja Fidler, Adela Barriuso, and Antonio Torralba. Scene parsing through ade20k dataset. In _Computer Vision and Pattern Recognition (CVPR)_ , pages 633–641, 2017. 6 

   - [153] Zhizhuo Zhou and Shubham Tulsiani. Sparsefusion: Distilling viewconditioned diffusion for 3d reconstruction. In _Computer Vision and Pattern Recognition (CVPR)_ , 2023. 9 

   - [154] Hao Zhu, Xinxin Zuo, Sen Wang, Xun Cao, and Ruigang Yang. Detailed human shape estimation from a single image by hierarchical mesh deformation. In _Computer Vision and Pattern Recognition (CVPR)_ , 2019. 2 

   - [155] Wojciech Zielonka, Timur Bagautdinov, Shunsuke Saito, Michael Zollh¨ofer, Justus Thies, and Javier Romero. Drivable 3D Gaussian Avatars. _arXiv preprint arXiv:2311.08581_ , 2023. 12 

   - [156] Christian Zimmermann, Duygu Ceylan, Jimei Yang, Bryan Russell, Max Argus, and Thomas Brox. Freihand: A dataset for markerless capture of hand pose and shape from single rgb images. In _International Conference on Computer Vision (ICCV)_ , 2019. 7 

- [136] Xueting Yang, Yihao Luo, Yuliang Xiu, Wei Wang, Hao Xu, and Zhaoxin Fan. D-IF: Uncertainty-aware Human Digitization via Implicit Distribution Field. In _International Conference on Computer Vision (ICCV)_ , 2023. 2 

- [137] Hongwei Yi, Chun-Hao P. Huang, Dimitrios Tzionas, Muhammed Kocabas, Mohamed Hassan, Siyu Tang, Justus Thies, and Michael J. Black. HumanAware Object Placement for Visual Environment Reconstruction. In _Computer Vision and Pattern Recognition (CVPR)_ , 2022. 5 

- [138] Tao Yu, Zerong Zheng, Kaiwen Guo, Pengpeng Liu, Qionghai Dai, and Yebin Liu. Function4D: Real-time Human Volumetric Capture from Very Sparse Consumer RGBD Sensors. In _Computer Vision and Pattern Recognition (CVPR)_ , 2021. 2, 3, 7 

- [139] Ye Yuan, Xueting Li, Yangyi Huang, Shalini De Mello, Koki Nagano, Jan Kautz, and Umar Iqbal. GAvatar: Animatable 3D Gaussian Avatars with Implicit Mesh Learning. _arXiv preprint arXiv:2312.11461_ , 2023. 12 

- [140] Ilya Zakharkin, Kirill Mazur, Artur Grigorev, and Victor Lempitsky. Pointbased modeling of human clothing. In _International Conference on Computer Vision (ICCV)_ , 2021. 2 

- [141] Yifei Zeng, Yuanxun Lu, Xinya Ji, Yao Yao, Hao Zhu, and Xun Cao. AvatarBooth: High-Quality and Customizable 3D Human Avatar Generation. _arXiv preprint:2306.09864_ , 2023. 3 

- [142] Hongwen Zhang, Yating Tian, Xinchi Zhou, Wanli Ouyang, Yebin Liu, Limin Wang, and Zhenan Sun. PyMAF: 3D Human Pose and Shape Regression with Pyramidal Mesh Alignment Feedback Loop. In _International Conference on Computer Vision (ICCV)_ , 2021. 2 

- [143] Huichao Zhang, Bowen Chen, Hao Yang, Liao Qu, Xu Wang, Li Chen, Chao Long, Feida Zhu, Kang Du, and Min Zheng. AvatarVerse: High-quality & Stable 3D Avatar Creation from Text and Pose. _arXiv preprint:2308.03610_ , 2023. 3 

- [144] Hongwen Zhang, Yating Tian, Yuxiang Zhang, Mengcheng Li, Liang An, Zhenan Sun, and Yebin Liu. PyMAF-X: Towards Well-aligned Full-body Model Regression from Monocular Images. _Transactions on Pattern Analysis and Machine Intelligence (TPAMI)_ , 2023. 2 

- [145] Hao Zhang, Yao Feng, Peter Kulits, Yandong Wen, Justus Thies, and Michael J. Black. TECA: Text-Guided Generation and Editing of Compositional 3D Avatars. In _International Conference on 3D Vision (3DV)_ , 2024. 3 

- [146] Jianfeng Zhang, Zihang Jiang, Dingdong Yang, Hongyi Xu, Yichun Shi, Guoxian Song, Zhongcong Xu, Xinchao Wang, and Jiashi Feng. Avatargen: a 3d generative model for animatable human avatars. In _European Conference on Computer Vision Workshops (ECCVw)_ , pages 668–685. Springer, 2023. 3 

- [147] Jason Y. Zhang, Sam Pepose, Hanbyul Joo, Deva Ramanan, Jitendra Malik, and Angjoo Kanazawa. Perceiving 3D Human-Object Spatial Arrangements from a Single Image in the Wild. In _European Conference on Computer Vision (ECCV)_ , pages 34–51, Cham, 2020. Springer International Publishing. 5 

- [148] Lvmin Zhang and Maneesh Agrawala. Adding conditional control to textto-image diffusion models. In _International Conference on Computer Vision (ICCV)_ , 2023. 12 

- [149] Yang Zheng, Ruizhi Shao, Yuxiang Zhang, Tao Yu, Zerong Zheng, Qionghai Dai, and Yebin Liu. DeepMultiCap: Performance Capture of Multiple Characters Using Sparse Multiview Cameras. In _International Conference on Computer Vision (ICCV)_ , 2021. 3 

1542 

Authorized licensed use limited to: Nazarbayev University. Downloaded on June 30,2026 at 07:49:14 UTC from IEEE Xplore.  Restrictions apply. 

