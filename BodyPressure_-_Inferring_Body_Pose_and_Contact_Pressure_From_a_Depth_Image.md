IEEE TRANSACTIONS ON PATTERN ANALYSIS AND MACHINE INTELLIGENCE, VOL. 45, NO. 1, JANUARY 2023 

137 

## BodyPressure - Inferring Body Pose and Contact Pressure From a Depth Image 

Henry M. Clever , Patrick L. Grady , Greg Turk, and Charles C. Kemp 

Abstract—Contact pressure between the human body and its surroundings has important implications. For example, it plays a role in comfort, safety, posture, and health. We present a method that infers contact pressure between a human body and a mattress from a depth image. Specifically, we focus on using a depth image from a downward facing camera to infer pressure on a body at rest in bed occluded by bedding, which is directly applicable to the prevention of pressure injuries in healthcare. Our approach involves augmenting a real dataset with synthetic data generated via a soft-body physics simulation of a human body, a mattress, a pressure sensing mat, and a blanket. We introduce a novel deep network that we trained on an augmented dataset and evaluated with real data. The network contains an embedded human body mesh model and uses a white-box model of depth and pressure image generation. Our network successfully infers body pose, outperforming prior work. It also infers contact pressure across a 3D mesh model of the human body, which is a novel capability, and does so in the presence of occlusion from blankets. 

Index Terms—Human pose estimation, bodies at rest, physics simulation, parametric human modeling, depth sensing, contact pressure, pressure injury 

## Ç 

## 1 INTRODUCTION 

Pstanding ailment for bedridden individuals, yet technol-RESSURE injuries are an extremely common and longogies to reliably detect them, such as pressure mats, remain expensive and rare in practice. Using a camera for this task could enable the widespread proliferation of pressure injury detection systems, reducing the 2.5 million of such injuries which occur in the U.S. every year [1]. However, sensing pressure from camera imagery faces substantial challenges: not only is the contact interface visually occluded by the human body itself, but the person is frequently covered with blankets, which makes it challenging to even sense where the person is in bed. 

We propose a method, BodyPressure, that can accurately infer body pose and contact pressure from a single image captured by a depth camera. With these constituents, BodyPressure can localize regions of high pressure underneath a person in bed by projecting the pressure onto a human model. We represent body pose with the Skinned Multi-Person Linear (SMPL) human model [2], which consists of a 3D volumetric mesh parameterized by 72 joint 

- Henry M. Clever, Patrick L. Grady, and Charles C. Kemp are with the Department of Biomedical Engineering, Georgia Institute of Technology, Atlanta, GA 30332 USA. E-mail: {henryclever, pgrady3}@gatech.edu, charlie.kemp@bme.gatech.edu. 

- Greg Turk is with the School of Interactive Computing, Georgia Institute of Technology, Atlanta, GA 30332 USA. E-mail: turk@cc.gatech.edu. 

Manuscript received 20 May 2021; revised 15 Oct. 2021; accepted 27 Dec. 2021. Date of publication 28 Mar. 2022; date of current version 5 Dec. 2022. This work was supported in part by National Science Foundation Graduate Research Fellowship Program under Grant DGE-1148903, in part by NSF award under Grant DGE-1545287, in part by NSF award under Grant IIS1514258, and in part by NSF award under Grant IIS-2024444, and AWS Cloud Credits for Research. 

(Corresponding author: Henry M. Clever.) Recommended for acceptance by C. Wolf. Digital Object Identifier no. 10.1109/TPAMI.2022.3158902 

angles and 10 body shape coefficients. Our approach takes as input a depth image taken by a camera looking down at a person underneath blankets, and infers a SMPL human model, as well as the contact pressure between the body and the mattress. 

To address the challenge of heavy occlusion when inferring human pose at rest, prior work has required multiple modalities as input, including RGB, depth, thermal, and pressure imagery [3], [4]. Our deep network, BodyPressureWnet, outperforms this prior work while using only depth images. This is made possible by adding a large synthetic dataset to a smaller real dataset. The depth modality has a number of benefits: it can be generated easily in simulation by rendering object geometry; deep learning models trained with synthetic depth images transfer well to the real world [5]; and depth imagery preserves patient privacy better than RGB imagery [6]. 

To create such a large collection of training samples, we employ fast physics simulations to generate BodyPressureSD, a synthetic dataset consisting of depth images, body poses, and pressure sensing mat data. We extend our previous work, Clever et al. [7], which simulates human bodies resting on a soft mattress with a pressure-sensing mat. We extend this method by generating blankets to cover the resting bodies, producing a set of meshes representing the bed, the person in bed, and the blanket covering the person (Fig. 1a). We then render these meshes to generate images similar to those captured by a real depth camera. This process can quickly generate data for training data-hungry deep models. We find that the synthetic depth images greatly boost performance of the deep model. 

We combine the synthetic data with real data from the Simultaneously-collected Lying Pose (SLP) dataset [3] to achieve a 9:1 mixed training data ratio. SLP offers well matched attributes for training and testing our methods. It includes co-registered depth and pressure images capturing 

This work is licensed under a Creative Commons Attribution 4.0 License. For more information, see https://creativecommons.org/licenses/by/4.0/ 

IEEE TRANSACTIONS ON PATTERN ANALYSIS AND MACHINE INTELLIGENCE, VOL. 45, NO. 1, JANUARY 2023 

138 

Fig. 1. We use fast physics simulations to generate BodyPressureSD, a large synthetic human resting pose dataset, and then train a deep model, BodyPressureWnet, to infer pose and pressure from a depth image. (a) Our simulation method rests bodies on a soft bed and covers them with blankets. We then render depth images from the perspective of an overhead camera, and generate pressure images from a pressure mat underneath the person. (b) Using an augmented dataset with a mix of this synthetic data combined with real data captured by a depth camera, we learn a mapping from depth and gender to pose and contact pressure. (c) This enables a camera to infer the pressure distribution of the person and potentially detect pressure injuries in the real world. 

diverse human resting poses in bed with varying scenarios of blanket occlusion, as well as 2D human pose annotations. To improve the ground truth pose labels, we present an optimization method to fit 3D SMPL bodies to the SLP dataset and publicly release the fits. We use these to supervise deep model learning, to test the model, and also to initialize the aforementioned synthetic data generator. Initializing the simulator with the appropriate pose distribution is important for generating realistic resting poses. 

Inferring the pressure distribution underneath a person from a depth image involves three main steps: (1) inferring human pose as a mesh model, (2) inferring the contact pressure on the top surface of the bed, and (3) projecting the pressure from the bed surface onto the body mesh. We introduce a network architecture to address this challenge, which uses a convolutional neural network (CNN) encoder to estimate parameters for the SMPL model. Our network uses depth and pressure map reconstruction components to improve accuracy. However, in contrast to other works which use black-box (learned neural network) reconstruction models [8], [9], [10], [11], we use a white-box (analytic) reconstruction technique. This reconstruction is computationally efficient, differentiable, and has no learned parameters. We refer to the reconstructions as maps instead of images to distinguish them from sensor data. 

In summary, our contributions include the following: 

A method, BodyPressure,[1] that takes as input depth images of a person in bed from an overhead camera and infers the body pose, contact pressure, and localized regions of high pressure density. 

BodyPressureSD, a synthetic dataset consisting of 97,495 bodies at rest with pressure images and depth images rendered with and without simulated blankets. 

SLP-3Dfits, a dataset consisting of 4,545 SMPL bodies [2] fit to the SLP dataset [3]. 

Section 2 covers related literature. Section 3 presents a method for annotating real data to create SLP-3Dfits. These annotations are used for initializing the synthetic data generator, for training the deep model, and for testing it. Section 4 presents our physics simulation pipeline for generating the synthetic training data. Section 5 presents our deep network architectures, which are trained using real and synthetic data. Section 6 explains how we evaluate our method, followed by the results and discussion in Section 7. 

## 2 RELATED WORK 

Sensor-Based Pressure Injury Monitoring. Commercial pressure mapping systems are among the most common methods of monitoring pressure injury risk, and have been used to more effectively reposition patients and reduce high pressure areas [12]. Researchers have made progress to improve monitoring through automatic bodypart localization [13], [14], [15] and posture detection [16]. An alternative to this is wearable pressure sensors that can adhere to at-risk areas [17]. The cost of these devices can deter widespread use, so others have studied how inertial measurement units (IMUs) can be used [18], among other methods [12]. Yet, peak pressure localization remains a challenge. The sacrum and heels have been noted as the most common areas, but also occur on the hips, elbows, ischium, shoulders, spinous process, ankles, toes, and head [19], [20]. 

Humans at Rest. While many works in computer vision model humans in active poses such as pedestrians crossing the street [21], resting belongs to a different class of human activity. Resting is characterized by a low degree of physical exertion, substantial contact with surrounding surfaces such as a bed or chair, and the fact that people spend an overwhelming portion of life resting. With the ability to learn complex mappings between images and labels using CNNs, researchers have inferred human resting pose from diverse human configurations, postures, and sensing modalities [3], [22], [23], [24], [25], [26], [27]. 

Maintaining awareness of scene constraints and dynamics can enable more physically plausible models of humans 

1. Code and data: github.com/Healthcare-Robotics/Body Pressure 

CLEVER ET AL.: BODYPRESSURE - INFERRING BODY POSE AND CONTACT PRESSURE FROM A DEPTH IMAGE 

139 

Fig. 2. We fit 3D SMPL bodies to the SLP dataset [3], which we use for initializing the physics simulator and for training and testing our deep models. Our method resolves depth ambiguity using a loss between the SMPL mesh and 3D points from the depth image. Examples are shown without the depth loss term, resulting in poses with depth error. Examples are also shown without BetaNet, resulting in bodies with unreasonable shapes. 

at rest. Chao et al. [28] used reinforcement learning to teach dynamic agents how to sit on a chair in a virtual environment. Hassan et al. [29] used optimization to infer pose in a way that the human model is consistent with its surroundings, i.e., not floating above a chair or sunk into it unrealistically. Our previous work modeled humans in bed using ragdoll physics [7], and another work synthesized human poses in arbitrary environments with objects that could be contacted or rested upon [30]. 

Simulating Human Environments. Approaches for generating synthetic data that model humans in the context of deep learning use physics simulators such as DART [31] and PyBullet [32], [33] and position-based dynamics simulators such as PhysX [34] and FleX [35]. In a recent work, we combined DART and FleX to rest kinematic human bodies on a soft mattress [7], and randomized the human pose and body shape to increase variability. Others have explored cloth with physics simulations [34], [36], [37], [38], which could be used to create a diverse set of blanket configurations and profiles on a person resting in bed. Human environment models can also benefit from understanding object motion landscapes [39] to synthesize better interactions [40]. 

Simulating Pressure and Depth Images. We refer the reader to our previous work on simulating pressure imagery [7], which includes a pressure image generation method that we use. For vision, RGB image synthesis relies on relatively complex graphics approaches [41], [42], [43] while creating synthetic depth images is more straightforward [44], [45]. Achilles et al. [22] generated depth data for a bed environment by simulating a blanket covering the person, and trained a deep network using this data. While this work is close in concept to ours, the human is represented with a skeleton, which has limitations, and the code and dataset are unavailable. To improve generalization performance, researchers have used noise models with pixel dropout, spot noise, and synthetic occlusion [3], [44], [46], [47]. Others have denoised real data during test time [48], at the cost of real-time inference speed. 

Annotating Datasets With 3D Human Mesh Models. Standard human pose datasets contain 2D keypoint annotations, which are pixel-wise joint position coordinate labels on images. Researchers have fit 3D human mesh models to these 2D keypoints by projecting a 3D body into image coordinates and optimizing over the human model parameters (e.g., kinematic joint angles) [49], [50]. Yin et al. [4] use the SPIN method [50] for fitting SMPL bodies to the SLP resting pose dataset. However, these methods suffer from depth 

perspective ambiguity. When additional information is present, such as 3D point clouds or scene geometry, it is possible to resolve these ambiguities, which Hassan et al. [29] showed. This can provide highly accurate annotations, but such optimizations require careful data preprocessing and are too slow to use during inference time. 

Deep Learning for 3D Human Pose Estimation. Inferring 3D human pose is a significant branch of research in computer vision [4], [7], [10], [29], [41], [42], [49], [50], [51], [52]. In recent years, deep learning has seen widespread use for inferring human pose, by using convolutional neural networks (CNNs) to encode features in an image and output some representation of human pose. We refer the reader to literature surveys for more comprehensive coverage [53], [54]. Here we discuss approaches that are relevant to the particular black-box and white-box architectures we use. Differentiable kinematic models embedded into image encoders have gained traction in research due to their ability to produce physically plausible human models [24], [51], [55], [56], [57]. In contrast to differentiable skeleton models, parametric human mesh models such as SMPL [2] offer a better representation of body shape and size. Both of our architectures use this. 

Many pose estimation methods incorporate black-box image reconstruction for purposes including heatmap regression [58], geometry awareness [10], and spatial residual error correction [11]. One such architecture that may be used for this is U-Net [8], which learns an image-to-image mapping with a latent space in the middle that can encode image classes [59] or physically meaningful features [60]. Fewer deep learning works have used white-box methods for image reconstruction, i.e., differentiable image generation methods with no learnable parameters. However, our previous work introduced a model of pressure map reconstruction [7] and was trained only with synthetic data, which we build on. 

## 3 ANNOTATING REAL DATA WITH SMPL BODIES 

Here we describe an optimization method for annotating an existing human pose dataset with 3D SMPL bodies, as shown in Fig. 2. This method finds body shape and pose parameters to fit the SMPL bodies to depth images and existing 2D keypoint annotations. The optimization includes terms for scene constraints, body mass, and height, if they are available in the dataset. By leveraging depth information, the method 

IEEE TRANSACTIONS ON PATTERN ANALYSIS AND MACHINE INTELLIGENCE, VOL. 45, NO. 1, JANUARY 2023 

140 

can resolve the ambiguities in pose which are inherent with 2D keypoint annotations alone. We annotate the SLP dataset [3] to create SLP-3Dfits, a dataset consisting of 3D fits to 4,545 unique poses as described in Section 3.2. SLP-3Dfits is used for initializing the synthetic data generation method described in Section 4, and evaluating the deep learning methods described in Section 5. 

Our optimization requires a depth image, D, capturing a real person who is not occluded by objects in the environment (e.g., blankets). A reprojection loss is computed between K 2D keypoints S 2 R[K][�][2] and 3D SMPL joint positions. Scene constraints, C, are used to reduce interpenetration between the body and the bed. Height and body mass measurements, h, m, are used to enforce physical consistency in the SMPL body shape, by modeling height and body mass as a function of SMPL body shape parameters. This is described in Section 3.1. We define the SMPL body parameters with **C** R ¼ ½ **b** R **Q** R **s** R **f** R�[>] , which contains the body shape parameters **b** R, the joint angles **Q** R, and the global translation and rotation **s** R, **f** R. Subscript R distinguishes the real data annotations from parameters in later sections. The optimization seeks **C** R that minimizes the objective function E as follows: 

**==> picture [214 x 25] intentionally omitted <==**

The error function contains the following terms: 

- EJ ð **C** R; SÞ penalizes the distance between 2D keypoint annotations and SMPL joints projected into camera space. 

- EDð **C** R; DÞ encourages a match between depth points and SMPL vertices visible from the camera’s perspective. This is implemented using a robust version [29] of the Chamfer Distance [61]. 

- EM ð **C** R; CÞ enforces scene constraints by penalizing interpenetration between the body and the mattress. 

- EP ð **C** RÞ penalizes body self-penetration, e.g., a hand interpenetrating through the chest. Collisions are detected using Bounding Volume Hierarchies [62]. 

- Ebð **C** R; h; mÞ encourages the SMPL shape parameters **b** R to express a body with a height and mass that match the participant’s measurements h; m. This requires a mapping from body shape to body height and mass, which is described in Section 3.1. 

During optimization, the joint angles **Q** R are constrained to values based on textbook joint angle limits [63], [64], [65]. The exact joint limits are provided in the code repository. Many datasets such as the SLP dataset [3] contain a variety of different poses for a particular person. Accordingly, all such posed bodies should have the same shape. To ensure that the SMPL shape parameters for each participant are identical across all data samples, the optimization was implemented as a batched optimization, allowing the joint optimization of body pose and shape across multiple samples. 

As the optimization of SMPL parameters **C** R provides a non-convex objective, the optimization may fall into local minima. To avoid this, each sample is initialized and optimized multiple times with different starting poses and orientations. The result with the lowest loss is selected. The 

optimization problem is solved using the ADAM differentiable optimizer. The method is similar to the approach used by Hassan et al. [29]; however, notable additions include our method of enforcing physical consistency on body height and mass, and our batched optimization that fits the same body shape across multiple pose samples. 

## 3.1 BetaNet 

To calculate Eb, we model body height and mass as a function of SMPL body shape parameters and gender, i.e., fh; mg ¼ fbð **b** ; **g** Þ, where h and m are values in units of meters and kilograms, respectively. Unlike **b** , height and weight are directly measurable physical values that can better constrain the network. Gender is modeled with two flags, i.e., **g** 2 R[2] , which may account for female ([0,1]), male ([1,0]), or gender-neutral ([1,1]) body models. In this work however, only female and male models are used. We represent the function fb with a 2-layer fully connected network, where the input consists of body shape parameters and gender, and the output is height and body mass. We train BetaNet on a large synthetic dataset consisting of randomly shaped SMPL bodies with known height and mass, and mass is modeled as a function of SMPL body mesh volume 

**==> picture [168 x 23] intentionally omitted <==**

where m� **g** is a gender-specific average body mass value we take from Tozeren [66], Vmesh; **g** is the volume of a gendered body model of interest, and V[�] mesh; **g** is the volume of a gendered body model with average shape **b** ¼ **0** . We train BetaNet with the following loss function: 

**==> picture [216 x 22] intentionally omitted <==**

where h[^] and m^ are the height and weight estimated by the network. Each term is normalized by standard deviations sh and sm, which are computed from the entire synthetic training dataset. The trained BetaNet is also used for the separate problem of learning a mapping from depth to pose and pressure, described in Section 5. 

## 3.2 SLP-3Dfits: SMPL Fitting to the SLP Dataset 

Here we describe how our method of fitting parametric SMPL bodies to depth images and keypoints is applied to the SLP [3] dataset, which contains 4,590 poses across 102 participants. We use these fits for initializing the physics simulator to generate synthetic data, for training our deep network, and for testing it. 

We annotate 4,545 poses across 101 participants (one subject is excluded due to a calibration issue). The SLP dataset contains calibrated, occlusion-free depth images (the ‘uncovered’ case) for every pose. After converting these to point clouds, points from the bed surface are filtered out with a height threshold, so that all points used in the objective function are from the surface of the human body. The SLP dataset also contains 2D keypoint annotations, body height, and body mass for all captured poses, which are 

CLEVER ET AL.: BODYPRESSURE - INFERRING BODY POSE AND CONTACT PRESSURE FROM A DEPTH IMAGE 

141 

Fig. 3. Our synthetic data generation method involves two processes: The first process is similar to our previous work [7]; it involves (I.) sampling random human poses, (II.) resting dynamic capsulized bodies on a soft bed to find a resting pose, (III.) resting a finer body representation on the bed to improve human body shape detail, and (IV.) using a simulated pressure sensing mat underneath the person to compute a pressure image. The second process involves (V.) covering the body with a blanket, (VI.) pulling the top of the blanket down to uncover the person’s head, (VII.) extracting deformed meshes, (VIII.) creating a solid mesh, and (IX.) simulating a depth image from a pinhole camera positioned above the bed. 

factored into the objective function. A plane representing the height of the bed surface is used as a scene constraint to limit penetration into the mattress. 

Generally the fits from the automatic optimization are of high quality. However, in some cases the result converges to an incorrect local minimum, usually when the participant is lying on their side and the hands are posed on the wrong side of the head. Thus, each result of the fitting process is manually checked by a human annotator for agreement with the original pose in the image data. For failure cases, the optimization is restarted with a different initialization and then re-checked. Roughly 9% of the fits required these restarts. The fits are of sufficient accuracy to use as ”ground-truth” for evaluation of neural network predictions, and we have made them available publicly. The mean error between the SMPL joint locations and the 2D skeleton annotations is 41.6 mm; per-joint error is provided in Appendix A, which can be found on the Computer Society Digital Library at http://doi.ieeecomputersociety.org/ 10.1109/TPAMI.2022.3158902. Note that the SLP dataset joint annotations have some offset when compared to the SMPL model joints, inflating this error metric. The average distance from the non-bed point cloud to the surface of the human model is 12.0 mm. 

model described in Section 5. BodyPressureSD contains 97,495 unique body shapes, poses, and image samples; data partitions are described in the evaluation (Section 6.1). 

The data generation pipeline consists of two processes, as depicted in Fig. 3. The first process (I. - VI.) is similar to that of our previous work [7]; it generates bodies resting on a soft bed with synthetic pressure images. The second process (V. - IX.) generates blanket occlusions on top of the bodies in bed with synthetic depth images. It uses three simulation tools: DART [31] for simulating articulated human dynamics; FleX [35] for simulating soft materials that include the human body, bed mattress, pressure sensing mat, and blanket dynamics; and PyRender [67] for depth image rendering. Some synthetic data examples are shown in Fig. 4. 

## 4.1 Simulating Bodies at Rest 

The process begins by sampling a large set of initial synthetic body poses, where each pose sample contains joint angles f **Q**[0] I[;] **[f]**[0] I[g][,][that][are][close][to][the][real][poses][f] **[Q]**[R][;] **[f]** R[g][fit] in Section 3. This is depicted in Fig. 3 I. Normally distributed noise is added to the hip, knee, inner shoulder, outer shoulder, and elbow joints. Each angle j in these joints receives noise with the following equation: 

**==> picture [185 x 13] intentionally omitted <==**

## 4 SYNTHETIC DATA GENERATION 

We present a synthetic data generation pipeline using physics simulations that is capable of creating a large dataset of humans resting. It can generate bodies at rest on a soft mattress with depth and pressure images. In practice, this approach is much more efficient than collecting comparable real-world data. The sole purpose of this pipeline is to create a large dataset, BodyPressureSD, for training the deep 

where fu[0] I;1[;][ u][0] I;2[;][ . . .][g ¼] **[Q]**[0] I[and][f][u][R;][1][;][ u][R;][2][;][ . . .][g ¼] **[Q]**[R][.][Other] joints are set equal to the real fit angles. The same amount of noise is added to two of the root angle joints representing the rotation of the body along its longitudinal axis (fR;2) and the rotation of the body normal to gravity (fR;3). No noise is added to fR;1, which represents rotation around the sagittal axis. For each pose, the body shape is sampled from a uniform distribution, following [68]: **b** ~ul3; 3 . | The 2D 

IEEE TRANSACTIONS ON PATTERN ANALYSIS AND MACHINE INTELLIGENCE, VOL. 45, NO. 1, JANUARY 2023 

142 

Fig. 4. BodyPressureSD synthetic data samples created by resting bodies on a mattress and covering them with a blanket. 

translation of the human body over the surface of the bed is also sampled from a uniform distribution: s[0] 1[; s][0] 2 u[0:2; 0:2 . The height of ] the body normal to gravity, s[0] 3[,][is] set according to the lowest initial point on the body so that every part of the body is initially above the bed. Accordingly, fs[0] 1[; s][0] 2[; s][0] 3[g ¼] **[s]**[0][. With the fully parameterized body of] initial shape and pose f **b** ; **Q**[0] I[;] **[f]**[0] I[; ] **[s]**[0][g][, body self-collisions are] checked using the capsulized body from SMLPify [49]. If there is a collision, the sample is rejected, otherwise, the set of parameters becomes f **b** ; **Q**[0] ; **f**[0] ; **s**[0] g. 

Two Physics Simulations. The first process uses physics simulations to convert a body with the initial collision-free pose f **b** ; **Q**[0] ; **f**[0] ; **s**[0] g to a resting pose f **b** ; **Q** ; **f** ; **s** g with human body mesh MH and pressure image P. It is the same process as our previous work [7], with the exception of the weighting method for the simulated body, which we updated. See details in Appendix B, available in the online supplemental material. Fig. 5 shows examples of resting poses and body shapes that are generated from a single SLP-3Dfits pose. The remainder of Section 4.1 provides a high-level summary of the methods from [7]. 

In Physics Simulation #1 (Fig. 3 II.), the human is modeled as an articulated rigid body made with capsule primitives. DART [31] is used to model this capsular human and simulate its dynamics. The articulated body uses the same joint angles and body shape parameters as the SMPL mesh, but unlike the mesh, the joint angles can change due to applied torques and forces (e.g., due to gravity and contact with the bed). At the same time, a different simulator, FleX [35], is used to model a mattress and a pressure-sensing mat underneath the body. FleX uses a unified particle representation to efficiently model deformable objects. These are combined in a loop to allow a dynamic articulated 

system (i.e., the body) to interact with soft materials (i.e., the pressure sensing mat). 

While the capsulized articulated rigid body from Physics Simulation #1 is well suited for modeling ragdoll physics and finding a resting pose, it does not represent the surface geometry of the human body with sufficient fidelity for pressure image generation. The process assigns the resting pose and body shape to a SMPL mesh and fills it with deformable FleX particles, which creates a non-articulated body with a finer profile of human features. This is depicted as Physics Simulation #2 in Fig. 3 III. This ‘particlized’ body is positioned above the bed with parameters f **b** ; **Q** ; **f** ; **s** þ Fa g, where the term g represents a vertical adjustment in the root joint translation so the body can be allowed to fall a short distance to settle on the bed a second time. 

The process uses polygon meshes to record the simulation state in Physics Simulation #2. Initially, the meshes include the undeformed human body, mattress, and pressure sensing mat meshes. The human body mesh is a function of the resting pose: M[0] H[¼][ f] ð **[b]**[;] **[Q]**[;] **[f]**[; ] **[s]**[ þ] g Þ. The mattress underneath the human is set to a twin size, consisting of a rectangular prism of particles in an undeformed mesh M[0] M[. The mattress is constructed using the same par-] ticlizing method as the human body [7]. The padded mat on the bed surface represents a layer of bedding underneath the person, and is constructed from a two-layer lattice of particles laced together by a grid of springs constraints, represented by mesh M[0] P[.][Physics][Simulation][#2][is][run][until] the particlized human body reaches static equilibrium, and then outputs mesh data for the resting human body MH, the deformed mattress MM , and the deformed pressure sensing mat MP . 

## 4.1.1 Synthesizing Pressure Imagery 

Fig. 5. Example of resting pose diversity. Left blue pose shows a SLP3Dfits example. Right black examples shows BodyPressureSD resting poses and body shapes that were initialized in the simulator by adding noise to the left blue pose (Eq. 4) and dropped on the mattress. 

Besides interacting physically with the capsulized body in Physics Simulation #1, the pressure sensing mat on the surface of the bed is also used to generate pressure images, based on particle penetration between the top (orange) and bottom (blue) layers of particles on the surface of the bed, shown in Fig. 3 IV. The simulated sensor measures pressure as a function of how far a top layer particle penetrates the underlying particles. Each penetration distance across the mat is converted into a value on pressure image P, which is 

CLEVER ET AL.: BODYPRESSURE - INFERRING BODY POSE AND CONTACT PRESSURE FROM A DEPTH IMAGE 

143 

also shown in Fig. 3 IV. We refer the reader to a prior work for further details about this process [7]. 

## 4.2 Simulating Blanket Occlusions 

Before simulating the cloth blanket, the process freezes the ending equilibrium state of Physics Simulation #2, which involves freezing particles representing the resting human, deformed mattress, and deformed pressure sensing mat. A blanket is created in FleX with a grid of particles shown in Fig. 3 V. The blanket is parameterized by two sets of terms: the blanket geometry terms, which determine blanket size, particle location, particle connection points and initial world transform; and the dynamic simulation terms, which determine the stiffness holding particles together. 

The blanket has an undeformed height and width hB and wB, which are chosen to represent a twin size of 1:68 � 2:29 meters, and are created with a 102 � 102 particle grid. The global translation is parameterized by fsB;1; sB;2; sB;3g ¼ **s** B 2 R3 and rotation by ffB;1; fB;2; fB;3g ¼ **f** B 2 R3. These can be used to incorporate domain randomization (e.g., by sampling random initial blanket translations) or to better match blanket configurations in a particular dataset. The blanket is initially set to a height sB;3 above the body so that the blanket does not initially collide with the body. The initial blanket configuration may be described by mesh M[0] B[¼] fðhB; wB; **s** B; **f** BÞ. The blanket is weighted with the same density as the mattress in the previous simulation. The blanket dynamics are also influenced by the blanket stiffness KB. 

The process then runs the simulation, dropping the soft blanket on the body in bed. Depending on the initial position over the surface of the body, the blanket may cover the human’s head, which is undesirable because it would likely not be a common occurrence in the real world. Thus, the blanket is adjusted by pulling on a set of particles on the top edge of the blanket - see Fig. 3 VI. To determine if the blanket should be pulled to uncover the human’s head, the process checks if the blanket is above the human’s neckline. In other cases, the top edge of the blanket may be initialized at a location very far from the human’s head, which could lead to the human being only partially covered. In this case, the algorithm checks if the blanket is below the human’s neckline, and if it is, the same set of particles is pulled upward to better cover the human. Once the blanket reaches static equilibrium, the simulator halts and outputs the deformed blanket as mesh MB. 

## 4.2.1 Rendering Synthetic Depth Imagery 

The process extracts the deformed meshes fMH; MM ; MP ; MBg as depicted in Fig. 3 VII., and records them as part of the dataset. Then, they are assembled using Pyrender [67], an open source python library for rendering and visualization (Fig. 3 VIII). Finally, the process renders D, a depth image from a camera facing the bed. Fig. 3 IX depicts two viewing angle perspectives, which include an observation from the side of the bed and an observation from mounting the camera directly above the bed facing downward. 

## 5 LEARNING POSE AND PRESSURE FROM DEPTH 

We train an algorithm that learns a mapping f from a depth image D captured over a person at rest with gender **g** , to a human mesh MH that models pose and body shape, and a 2D array P that encodes the contact pressure on the surface of the mattress underneath the person 

**==> picture [177 x 10] intentionally omitted <==**

We represent f in the form of a deep network. The body mesh MH and the pressure array P can be used to calculate the pressure distribution on the surface of the body, Pb (recall Fig. 1c), which contains localized pressure on specific body parts. We define Pb as a collection of human body mesh vertices that are each assigned a pressure value due to contact from the underlying surface. Because the mesh MH is learned with a 6-DOF pose in the world reference frame and the contact pressure array P is collected by a sensor mounted at a known position in the world, they are implicitly co-registered. Assuming that the pressure mat exists within a flat plane normal to gravity on the top surface of the bed, each contact pressure element pxy may be projected normal to gravity onto the human mesh, where pxy is assigned to mesh vertex vj if its taxel area contains the x; y position of vj. A taxel is defined as a tactile pixel on a forcesensing array [7]. This mapping approximates the complex phenomena that occur when the mat is deformed due to contact by neglecting stretching and folding. As such, 

**==> picture [166 x 10] intentionally omitted <==**

This projection is sufficient to localize pressure on specific body parts, because vertex indices on the SMPL model are independent of body pose and shape, i.e., a heel vertex is always on the heel. Vertices above the undeformed bed height are set to zero because they are not in contact, and vertices with non-zero pressure are required to be unoccluded from the pressure mat by other body parts or surfaces of the body. The latter is ensured by casting a ray downwards from each vertex toward the mat and checking if it passes through any triangular faces. If it passes through a face, the pressure is set to zero. This will ignore pressure due to self contact between parts of the body. 

## 5.1 BodyPressureWnet 

Here we describe BodyPressureWnet (BPWnet), a deep network with a white-box model of depth and pressure image generation, shown in Fig. 6. BPWnet uses a traditional CNN for encoding depth images, but uses a white-box model for reconstructing depth and pressure images from an embedded SMPL human model. These white-box models are analytic and fully observable with no learned parameters, and are also differentiable. BPWnet contains two modules: ‘Mod1’, which produces an initial estimate, and ‘Mod2’, which refines the estimate through residual error in a similar way to previous works [7], [11], [69]. 

**Cb** using a CNN. From there, it uses the differentiable SMPLFirst, BPWnet maps a depth image D to SMPL parameters embedding from Kanazawa et al. [51] to produce a SMPL mesh estimate, M[c] H. A loss is applied using height and 

IEEE TRANSACTIONS ON PATTERN ANALYSIS AND MACHINE INTELLIGENCE, VOL. 45, NO. 1, JANUARY 2023 

144 

Fig. 6. BodyPressureWnet (BPWnet), a deep network that learns a mapping from depth and gender to pose and contact pressure. Depth, D is encoded with a black-box CNN and outputs SMPL [2] human model parameters **C[b]** , which is used to reconstruct a SMPL human mesh M[c] H . Using white-box image reconstruction components DMR and PMR, it refines the pose estimate and outputs a pressure map. The pressure map features are calibrated with CAL to produce a contact pressure estimate P[b] . The two module design refine estimates with initial and residual stages; subscripts 1 and 2 indicate estimates from each module, respectively. 

weight estimates from BetaNet. The first module, Mod1, contains a white-box model of depth image generation, which reconstructs depth maps D[b][þ] from a SMPL mesh. The spatial residual between these maps and the input depth images are used to learn a correction and refine initial human pose estimates in the second module, Mod2. In contrast to Mod1, Mod2 contains a white-box model of pressure image generation, which differentiably reconstructs pressure maps P[b][þ] from an improved SMPL mesh estimate. Finally, the CAL component in Fig. 6 adjusts pressure maps to achieve a similar calibration to real pressure images. 

Depth Image Encoding. Both modules of BPWnet encode depth imagery with ResNet34 convolutional neural networks (CNNs). Each CNN outputs estimated SMPL parameters **C**[b] ¼ **b^ Qb s^ x^ y^** b^ >2 R[89] , which contains body shape, joint h i 

angles, and root translation and rotation. It also contains an estimated distance between the camera and the bed, b[^] , which is described later in this section. The SMPL parameters are used to compute a SMPL human mesh model with no learnable weights. The SMPL block takes as additional input a set of gender flags **g** 2 R[2] (recall Section 3.1) and outputs a human mesh M[c] H. We define a loss on the SMPL model, LSMPL, which minimizes error from the SMPL parameters and 3D SMPL joint positions. We also define a loss on the 

SMPL vertex positions, Lv2v, which can be used in conjunction with LSMPL to provide more supervision at a marginally higher computational cost. Appendix C, available in the online supplemental material, contains details on LSMPL and Lv2v. BPWnet also provides supervision on human mass and height using the BetaNet described in Section 3.1. tionWhite-Box(DMR) moduleDecoding.computesIn Mod1, the deptha depth mapmap reconstruc-Dbþ 2 R64 x 27 from the body mesh M[c] H;1. This is computed by calculating the distance between the camera plane and the inferred human mesh (Fig. 7 - left). The reconstructed depth map is used for residual error refinement in Mod2: The difference between the real pose in the input depth image D and 

bþ the pose in the reconstructed depth map D contains information that can be used to improve the initial pose and body shape estimate. This white-box model of depth image generation is similar to the pressure image generation introduced in our previous work [7]. Unlikebþ the input depth image D, the DMR reconstruction D only contains human mesh information and is occlusion-free; specifically, it does not contain blanket or mattress information because its sole purpose is to improve the initial pose estimate. 

to Mod2computeusesa pressurepressure mapmap reconstructionP[b] þ 2 R64 x 27 from(PMR)thefromrefined[7] pose estimate M[c] H;2. This is the distance the body mesh sinks into the underlying mattress (Fig. 7 - right). In contrast to the previous work that reconstructs a pressure map from a pressure image, in BPWnet, PMR reconstructs a pressure map from a depth image. The position of the mattress must be known with high accuracy relative to the depth camera, because the pressure is sensitive to small changes in the vertical distance between the camera and bed. Small camera movements or the weight of a large person on the bed can 

Fig. 7. Differentiable white-box depth and pressure map reconstruction. DMR computes a linear depth map D[þ] between the height of the camera and the top surface of the human mesh (left). PMR computes a linear pressure map P[þ] between the undeformed height of the surface of the bed and the human mesh (right). Variable b is the distance between the camera and the bed. 

CLEVER ET AL.: BODYPRESSURE - INFERRING BODY POSE AND CONTACT PRESSURE FROM A DEPTH IMAGE 

145 

change the perceived distance enough to alter the reconstructed pressure map. Thus, it requires an additional variable to represent changes in the vertical distance between the camera and the surface of the bed, which can correct for changes in the camera’s position. We define this parameter as b, and learn it from depth images at varying distance from the bed. We also define a loss on the PMR component, LPþ , which can be used to train the depth image encoder. See details in Appendix C, available in the online supplemental material. 

Calibrating the Inferred Pressure Map. While P[b] þ is spatially similar to a pressure image, it has some qualitative differences: it contains more dilated features (i.e., the spread of a given pressure point is wider), it has less noise, and the magnitude of each pixel is a distance rather than a pressure. Thus, our approachþ uses a small convolutionalb network, CAL, to calibrate P[b] , converting it to P 2 Rb[64] þ[�][27] . CAL takes as input a stack of 3 images including P and constant CoordConv maps R 2 R[2][�][64][�][27] , which allow the network to model non-translation invariant aspects and can improve trainability and generalization [70]. CAL contains 4 layers of convolution, with < 0:4% as many parameters as the encoder. We define a loss based on the output pressure image, LP, which can be used to train CAL. See Appendix C, available in the online supplemental material. 

## 5.1.1 Training Strategy 

We train the encoders for Mod1 and Mod2 separately. The loss for Mod1 is computed as 

**==> picture [194 x 11] intentionally omitted <==**

where BetaNet is separately pretrained (Section 3.1) and contains frozen network weights. Then, the entire dataset is passed forward through the network to compute a set of Mod1 estimates with each sample containing f **C[b]** 1; D[b][þ] ;[b] Cdþ g, where[b] Cdþ are the binary maps of D[b][þ] , created by setting background depth values on the bed surface to zero and all higher values corresponding to the human surface to one. The purpose of binary maps is to help the network learn from small values on the human surface that are important, yet distinct from the zero values on the bed surface. In this forward pass, noise is added to the SMPL parameters to increase the variation in the types of error that þMod2 **b** corrects. With a dataset consisting of inputs f **D** ; **D[b]** ; **C** dþ g, we train Mod2 to learn a residual correction ð **C[b]** 2 � **C[b]** 1Þ with the following loss: 

**==> picture [226 x 14] intentionally omitted <==**

After training the depth image encoders, we train the CAL network. CAL learns to refine the features of P[b][þ] and calibrate pressure values at individual taxels rather than to spatially adjust pressure for a change in limb or body movement. Ground truth human meshes from the dataset are used to compute ground truth reconstructed pressure maps P[þ] , which are fed into CAL during training. CAL outputs the estimate P[b] , which is compared to ground truth P during training, using loss LP. 

## 6 EVALUATION 

We evaluate our method using the SLP multimodal dataset [3], which is a human pose dataset consisting of 4,590 unique resting poses in bed across 102 human participants. Each pose is captured with three different situations of varying visual occlusion: (1) thin sheet covering the person, (2) thicker blanket covering, and (3) no covering. The dataset contains RGB, depth, point cloud, thermal, and pressure imagery, as well as 2D human pose keypoints; the bottom row of Figs. 1b and 2 provide a couple examples. In Section 6.1, we describe the data partitions generated using the method in Section 4. Finally, in Section 6.2, we describe the evaluation of the deep network from Section 5 on the SLP dataset. 

## 6.1 BodyPressureSD Synthetic Dataset Partitions 

The synthetic data generation method from Section 4 is used to generate BodyPressureSD: a large collection of samples, each of which includes a resting pose, a unique body shape, a gender, a depth image, a pressure image, and four meshes from the scene for the person, mattress, pressure sensing mat, and blanket. The pressure images for both this data and the real SLP data are normalized by body mass. The depth and pressure images are spatially co-registered with the calibrated images in the real SLP dataset. Details on these procedures are provided in Appendices F and G, available in the online supplemental material. 

Human Body Pose Partitions. To create the synthetic training dataset, our process samples initial poses and body shapes close to the real poses as depicted in Fig. 3 I. For each unique real pose among the 80 training subjects in the SLP dataset, it attempts to generate 30 initial synthetic poses split evenly between female and male SMPL bodies. Each of these poses have a unique body shape. Given 80 participants in the training dataset with 45 unique poses per participant, this would ideally generate 30 � 80 � 45 ¼ 108; 000 initial poses and body shapes. However, in some cases it is challenging to find a collision-free pose for a particular body shape that is close to a particular real pose, so some samples are aborted when a limit is reached. This reduces the initial pose/body shape count to 103,966. 

Next, the process runs this set of bodies with initial poses through Physics Simulations #1 and #2, of which some more are rejected due to the simulation becoming unstable. The process is designed to automatically detect when simulation instability is imminent, in which case it aborts the simulation and rejects the pose. This can happen due to situations such as a limb poking a hole in the pressure mat, which are described in our previous work [7]. None of the blanket covering simulations resulted in instability. This resulted in a total of 97,495 unique data samples, which are used to train the network. The data partitions are broken down in Table 1. 

Blanket Configuration Partitions. The SLP dataset contains both thick and thin covers, which are placed to cover most of the body. The simulator is only equipped to generate blankets with a single fixed thickness, which we assume is close enough to represent both real coverings. The real blankets often contain many wrinkle features that may be caused by pulling or adjusting the blanket so that it covers 

IEEE TRANSACTIONS ON PATTERN ANALYSIS AND MACHINE INTELLIGENCE, VOL. 45, NO. 1, JANUARY 2023 

146 

TABLE 1 

Human Pose and Body Shape Dataset Partitions 

|Description<br>Supine - Unique Images w Blankets<br>L. Lateral - Unique Images w Blankets<br>R. Lateral - Unique Images w Blankets<br>Supine - Unique Images w/o Blankets<br>L. Lateral - Unique Images w/o Blankets|synthetic<br>train ct.<br>34619<br>32050<br>30826<br>34619<br> 32050|real<br>train<br>ct.<br>2370<br>2370<br>2370<br>1185<br>1185|real<br>test<br>ct.<br>660<br>660<br>660<br>330<br>330|
|---|---|---|---|
|R. Lateral - Unique Images w/o|30826|1185|330|
|Blankets||||
|Total Unique Images<br>Supine - Unique Poses<br>Right Lateral - Unique Poses<br>Left Lateral - Unique Poses<br>Total Unique Poses<br>Total Unique Body Shapes|194990<br>34619<br>32050<br>30826<br>97495<br>97495|10665 <br>1185<br>1185<br>1185<br>3555<br>79|2970<br>330<br>330<br>330<br>990<br>22|
|Num Samples for Training and Testing|97495|10665|2970|



the body appropriately. We attempt to mimic these situations. The process incorporates randomization in the initial position of the blanket over the surface of the bed **s** B (recall the top half of Fig. 3 V). Each resting body is associated with a single initial blanket position and the covering variation that results from it. The initial blanket configurations are split into two partitions. In the first, the blanket is centered over the person with the upper edge coinciding with the person’s neckline, such that no pulling is required to uncover the head or cover the body (recall Fig. 3 VI.). In the second partition, the initial blanket position is randomly sampled across the person in bed. These two blanket configuration scenarios are split 50/50 among the synthetic data pose partitions described in Table 1. In all cases, the initial blanket rotation, **f** B, is set to a constant value of **0** . Appendix E, available in the online supplemental material, provides details on the specific sampling bounds. 

## 6.2 Network Evaluation 

For human pose inference, we compare our method to the Pyramid fusion scheme by Yin et al. [4], which uses 4 modalities (RGB, depth, thermal, and pressure imagery) to infer a SMPL mesh. Our method uses only depth imagery, which would have significant advantages for real-world deployment. Pose accuracy is evaluated with 3D mean-per-joint position error (MPJPE), using the same 22-subject test set proposed in Yin et al. For each pose sample, the inferred positions of 24 joints on the SMPL model are compared to ground truth using 3D euclidean error. 

For both contact pressure inference and the inferrence of pressure on the human body, we did not find any existing work for comparison. We designed a second deep architecture to compare BPWnet with, which uses a more traditional black-box method of image reconstruction. We refer to this alternative as BodyPressureBnet (BPBnet). BPBnet replaces the white-box DMR and PMR components in BPWnet with black-box decoders. These learned image decoders are designed symmetrically to the encoders, 

expanding the SMPL parameters back into images. Appendix D, available in the online supplemental material, contains details about BPBnet. We train both network architectures with the same hyperparameters, and compare the inferred pressure image to ground truth using meansquared error (MSE), which is computed on a per-taxel basis. We compare the ability to localize regions of high pressure density using vertex-to-vertex pressure (v2vP) mapped to the SMPL model, where MSE is computed on a per-vertex basis. Because vertices are not evenly distributed over the surface of the body and pressure is in units of force=area, the pressure on each vertex is normalized by the average area of the adjacent triangles. We also compare human pose estimation error between BPWnet and BPBnet. 

Dataset Splits. We trained on datasets consisting of real, synthetic, and combined synthetic and real data. For the synthetic training data, we selected depth images with blanket occlusions on 2=3 of the poses, and depth images without blankets for 1=3 of the poses. This matches the real data, of which 2=3 of images are occluded by blankets 1=3 are not. We performed validation and testing on real data. We created both training/validation and training/testing splits based on the 102 subjects in the SLP dataset. For training/ validation, we trained on data from the first 70 subjects (i.e., subjects 1 - 70, with 9,315 real and 85,114 synthetic samples), and validated on the next 10 subjects (i.e., subjects 71 - 80, with 1,350 real samples). We used this split for tuning network hyper parameters. For training/testing, we used the same split as Yin et al. [4], and trained on data from the first 80 subjects (i.e., subjects 1 - 80, with 10,665 real and 97,495 synthetic samples), and tested on the last 22 subjects (i.e., subjects 81 - 102, with 2,970 real samples). We did not use subject 7 data due to errors in calibration. 

Depth Image Noise Model. Our camera noise model includes white noise, dropout, and synthetic occlusion on sections of the input image using the code provided by Liu et al. [3]. Because the inferred contact pressure is highly sensitive to the distance between the camera and the bed, a single distance is uniformly sampled between -5 and 5 cm for each image, which is added to all depth pixels to make the inference robust to vertical movements of the camera or bed. No rotational noise or translational noise in the plane normal to gravity are added, since they appeared to be unnecessary for the SLP dataset. Noise is also added to account for the physics of the bed springs underneath the soft mattress. The simulated mattress is set on a rigid plane, which differs from the flexible springs in Invacare Homecare bed used to collected real data in [7] as well the bed used to collect the SLP dataset [3]. In practice, we observe a substantial drop in the middle of the bed when a person rests on it. This is modeled with a 2D parabolic map added to depth images during training, which is equal to zero at the edges of the bed and increases to a max in the center. A parameter that alters this max value is uniformly sampled between 0 and 10 cm. 

Network Hyper-Parameters. For all networks, we shuffled the training data, used a batch size of 128, used the ADAM optimizer [71] for gradient computation, and used a learning rate of 0.0001 and weight decay of 0.0005. For BetaNet, we trained for 500 epochs on real and synthetic data. The BetaNet used in the optimization of Section 3 was only 

CLEVER ET AL.: BODYPRESSURE - INFERRING BODY POSE AND CONTACT PRESSURE FROM A DEPTH IMAGE 

147 

TABLE 2 

Human Pose Estimation (Pose), Contact Pressure (P. Img.), and Pressure Distribution (v2vP) Error Results When Evaluating on the 22 Subject Test Set 

**==> picture [492 x 119] intentionally omitted <==**

yindicates the encoder was trained with 108K mixed, while the CAL component was trained using only 11K real. 

trained with synthetic data because the body shape parameters were not available prior to annotation. For the CAL network in BPWnet, we trained for 500 epochs on real and synthetic data. For both BPBnet and BPWnet, we trained on 100 epochs on the first module. Then, we pre-computed their estimates and used it for training the second module, which we trained for 40 epochs. We trained for 40 epochs because the network began to overfit the training data at this point regardless of the training dataset used. Our machine has a AMD Ryzen Threadripper 1950X 16-Core processor with 64 GB of CPU RAM and a NVIDIA RTX3090 GPU. Training CNN1 and CNN2 network modules each took � 12 hrs, while BetaNet and CAL took < 3 hrs. Overall, BPWnet had better computational performance than BPBnet, which is detailed in Appendix H, available in the online supplemental material. 

## 7 RESULTS AND DISCUSSION 

In this section, we present and discuss the results. 

Our Method for Estimating Pose Outperforms the State-ofthe-Art. Using only a depth image in the input, BPWnet is able to infer pose with 12% lower error than the state-of-theart method from [4], which uses a combination of RGB, depth, thermal, and pressure imagery to infer pose. We note that Yin et al. [4] use a different ground truth fitting method from [50], but their fits and code are not released so we compare to their reported error. BPWnet also outperformed the alternative BPBnet. Table 2 presents these results, with comparisons between the type of covering on the person. Fig. 8 presents a visual overview of BPWnet. 

Mixing Synthetic and Real Data Boosts Performance. When training the network only on real depth images from the SLP dataset or only on synthetic depth images from BodyPressureSD, performance lags. However, when the real and synthetic datasets are naively mixed into a single bag of training data, pose error drops by more than 30%. 

Our Method Can Infer Contact Pressure From Depth. Our method can infer a pressure image (P) from overhead depth imagery, which is also depicted visually in Fig. 8. Like pose inference, using a mixed bag of synthetic and real data boosts performance, as shown in Table 2. The error for BPBnet is significantly lower than BPWnet. When the SMPL model is ablated from BPBnet, it is still able to infer pressure but performs worse. This indicates that joint learning of the SMPL parameters helps BPBnet learn contact pressure from depth. We did not ablate the SMPL model from BPWnet because it requires SMPL to infer a pressure image. 

BPWnet Can Infer Pressure on the Body. While black-box image reconstruction is far more common in computer vision and our black-box model (BPBnet) has a lower pressure image inference error, our white-box model (BPWnet) has a lower pressure distribution (Pb) error as measured by vertex-to-vertex pressure (v2vP) in Table 2. We provide additional v2vP results on common pressure injury risk regions in Table 3 and depict the segmentation of the risk regions on the SMPL mesh in Fig. 9. 

Generally, BPWnet can more reliably localize pressure than BPBnet. This is because the inferred pressure image in BPWnet can be reduced to a function of only the SMPL parameters (i.e., P[b] ¼ fð **C[b]** Þ ) where the spatial mapping between the human mesh M[c] H and the pressure map P[b][þ] is a known geometric function with no learnable parameters, so the reconstructed pressure image reliably projects onto the surface of the inferred human mesh. In contrast, there is little in the black-box model to ensure the inferred pressure map spatially co-registers with the inferred mesh. We present a visual example of this phenomena in Fig. 10. In it, the person lays supine on the bed with the left foot tucked under the right upper leg. This produces a peak pressure on the left foot, which carries extra weight from the right leg. BPWnet appropriately projects the peak pressure onto the left foot, while the BPBnet projection contains a discrepancy in the peak pressure location. 

TABLE 3 

Pressure Distribution - v2vP, MSE (kPa[2] ) Error Comparison Across Common Pressure Injury Risk Regions [19], [20] 

|Network||Head|L. heel|R. heel|R. hip|L. hip L. shoulder|Sacrum R. shoulder|L. elbow|L. toes|R. toes|R. elbow|Ischium|Spine|
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|BPWnet,|108Ky|3.609|3.217|2.946|2.524|2.371<br>1.774|1.704<br>1.624|1.196|1.188|1.180|1.105|0.650|0.441|



IEEE TRANSACTIONS ON PATTERN ANALYSIS AND MACHINE INTELLIGENCE, VOL. 45, NO. 1, JANUARY 2023 

148 

Fig. 8. Results: Inferring pose, contact pressure, and localized pressure distribution from depth using BPWnet. Showing real data with people occluded by blankets in the depth images. All cases are from the last 22 test subjects in the SLP dataset; white coverings indicate ‘cover 1’ and black indicate ‘cover 2.’ The far right renderings in each group are a mirror flip because they show the pressure distribution underneath the body; the top shows an inferred pose while the bottom shows a pose from the SLP-3Dfits annotations. 

CLEVER ET AL.: BODYPRESSURE - INFERRING BODY POSE AND CONTACT PRESSURE FROM A DEPTH IMAGE 

149 

Fig. 9. SMPL segmentation into pressure injury risk areas. 

Pose versus Contact Pressure Accuracy Tradeoff. A number of factors may account for the tradeoff in pose versus contact pressure accuracy between BPWnet and BPBnet. For pose estimation, the reconstructed depth map estimate D[b][þ] in BPWnet is a constrained function of SMPL parameters and thus provides more consistent spatial residual feedback to learn the pose correction in Mod2. If the input depth image is highly occluded or contains noise, BPWnet may produce a poor initial pose estimate but D[b][þ] will contain no less pose information. In contrast, the black-box reconstructed depth map in BPBnet has no lower bound on the amount of information it contains, so in some cases it may not contain any useful information for the correction. 

For the pressure image inference, Table 2 indicates that the SMPL model is not necessary for inferring the pressure image with BPBnet. Thus, a pixel-to-pixel black-box network is sufficient for inferring a pressure image from an occluded depth image. BPWnet likely decreases the performance of this inference because it has fewer free parameters and a tighter grasp on the pressure image formation process: if the pose changes, the pressure necessarily changes. Some poses may be more challenging to learn than some instances of contact pressure, so an inaccurate pose would adversely affect the pressure image inference. 

Ablating BPWnet Components Reduces the Performance of Body Pressure Inference. We conducted an ablation study to test the importance of components in BPWnet, shown in Table 4. We ablated BetaNet, which improved pose accuracy, marginally reduced pressure accuracy, and substantially reduced accuracy of body height and weight. Coincidentally, the BetaNet model of height and mass also seems to cause a tradeoff in pose versus pressure accuracy. However, the reduction in overall body shape accuracy as measured by height and weight casts some doubt on the merit of omitting BetaNet. We ablated the CAL feature calibration component, which affects only the contact pressure inference. Without CAL, the pressure inference performs poorly because the overall scale of the PMR output, P[þ] is 

Fig. 10. Behavior comparison of BPBnet and BPWnet. BPBnet has lower contact pressure error, but its projection onto the inferred mesh contains an artefact. BPWnet plausibly infers a high pressure on the foot, while BPBnet incorrectly assigns a high pressure to the underside of the upper leg. 

different than P. This indicates that CAL is able to scale the pressure from an arbitrary range to an appropriate range. We also ablated the residual learning by removing the DMR component in Mod1 and used PMR instead to compute pressure maps. For this, we trained only the initial CNN for 100 epochs but used the LBPW2 loss. This marginally changed pose, pressure, and body height error but substantially reduced the accuracy of body weight. 

CAL Succeeds at Both Scaling and Locally Calibrating Pressure Map Features. Recall that the purpose of CAL is to calibrate P[þ] both by scaling it and by adjusting local features to better resemble features in the real pressure image P. We tested the ability to achieve each of these purposes by adding a body mass normalization component to the output, which scales P[þ] to the correct pressure range. The estimated body mass from BetaNet was used for this and the results are shown in Table 5. Without CAL, mass normalization greatly improves the pressure inference, but not to the extent that CAL does. This indicates that CAL does more to improve the features in P[þ] than only scaling it. We also compared a network that both uses CAL and normalizes by mass, and observed a slight dip in performance. 

Improvements to Blanket Simulation May Improve Performance. When training using only synthetic data (with and without blanket occlusions), pose estimation is substantially better when testing on real depth images that do not have blanket occlusions than testing on those that do. See Table 2 for reference. The same holds true when training on mixed 

TABLE 4 

Ablation Study - Evaluated on the 22 Subject Test Set 

|Network||Residual<br>w/DMR<br>BetaNet CAL feature<br>calibration|Overall - Pose<br>MPJPE(mm)|Overall - P. Img.<br>MSE(kPa2)|Overall - v2vP<br>MSE(kPa2)|Body mass<br>MAE(kg)|Body height<br>MAE(mm)|
|---|---|---|---|---|---|---|---|
|BPWnet, 108K|BPWnet, 108Ky|x<br>x|72.84|1.215|2.470|7.42|44.35|
|BPWnet, 108K|BPWnet, 108Ky|68.62<br>~~xx~~||1.296|2.494|7.62|65.97|
|BPWnet, 108K|BPWnet, 108Ky|x<br>x|69.36|16.326|31.806|5.64|39.45|
|BPWnet, 108K|BPWnet, 108Ky|x<br>x<br>x|69.36|1.184|2.439|5.64|39.45|



Pose and pressure error shown with same metrics as previous tables. Body mass and height are evaluated with mean absolute error. 

IEEE TRANSACTIONS ON PATTERN ANALYSIS AND MACHINE INTELLIGENCE, VOL. 45, NO. 1, JANUARY 2023 

150 

TABLE 5 

|TABLE 5<br>(a)|TABLE 5<br>(a)|TABLE 5<br>(a)|TABLE 5<br>(a)|
|---|---|---|---|
|CAL Feature Calibration Test - Evaluated on the 22 Subject<br>Test Set<br>Network<br>Normalize<br>by body<br>mass<br>CAL<br>feature<br>calibration<br>Overall - P.<br>Img. MSE<br>(kPa2)<br>Overall -<br>v2vP MSE<br>(kPa2)<br>BPWnet, 108Ky<br>16.326<br>31.806<br>BPWnet, 108Ky<br>1.393<br>2.713<br>(a)<br>~~Ee~~||||
|BPWnet, 108Ky||1.195<br>2.485||
|BPWnet, 108Ky||1.184<br>2.439||



Pressure error shown with same metrics as previous tables. 

synthetic and real data. On the other hand, when training using only real data (with and without blanket occlusions), pose estimation accuracy is comparable when testing on real depth images with and without blanket occlusions. This seems to indicate that the quality of synthetic blanket occlusions could be improved. 

We manually adjusted simulation parameters to achieve realistic blanket folding characteristics. Besides blanket stiffness, we found that other FleX parameters such as the number of simulation substeps had an impact on the cloth behavior. Optimizing the synthetic blanket parameters to make them behave more like real coverings may improve the quality of synthetic data and boost performance when testing on real depth images with blanket occlusions; for example, the methods from Runia et al. [72] might merit future exploration. 

Body Pressure Loss May Improve Performance. The loss functions in BPWnet and BPBnet include terms computed at many different locations to provide better supervision. A loss directly computed based on the error in the inferred body pressure Pb merits future investigation. Recent differentiable geometry tools may enable such a loss computation and improve performance. 

Released Materials Can Support Future Work. In addition to the SLP-3Dfits human body annotations and the BodyPressureSD synthetic dataset used to train our model, we publicly release 3D synthetic mesh data for the resting human, mattress, pressure mat, and blanket. This may be useful for future work in the area of geometric learning. 

## 8 OPPORTUNITIES FOR FUTURE WORK 

While BPWnet exhibits promising performance and demonstrates the feasibility of using a depth sensor to infer body pressure, further research will be required to establish its clinical effectiveness. For example, the occurrence of false positives or false negatives may limit the system’s ability to detect when a pressure injury is imminent. One example of a false negative is in the top left of case Fig. 11a, where there is a peak pressure region on the person’s right shoulder, but the system indicates there is no pressure on the right shoulder. The ability of the current network to generalize to clinical settings is also unclear. For example, pillows, nearby furniture, different types of bedding, medical instrumentation, and objects in bed, such as a mobile phone and other devices, would likely result in errors. 

Some types of errors might be difficult or impossible to overcome with a single frame from a depth camera. For example, in the top left error example in Fig. 11a, the 

Fig. 11. (a) Examples of errors when testing with BPWnet. (b) Limb interpenetration scenarios, also with BPWnet. 

person’s elbow and knee are elevated such that they push the blanket up into a tent like shape that reduces contact between the blanket and the person’s body. This reduces depth information about the body surface and the system makes errors, including neglecting pressure on the hidden leg and one side of the body. 

For other types of errors, future work might achieve better performance. Fig. 11a shows examples of errors. On the top right, the sheet covering the bed folds upwards and the system mistakes it for the person’s right leg. On the bottom left, the person crosses their right foot on top of their left knee and the system incorrectly estimates that the knee is on top of the foot. This leads the system to infer a peak pressure on the heel, rather than the calf. On the bottom right, the person assumes a pose that would be unusual when sleeping. The person rests their head on their left hand. The system misestimates the arm poses. Additionally, the annotation method incorrectly labels the left hand as being behind the head rather than supporting it. 

Other errors relate to the body contacting itself. The network can output unnatural body part interpenetration. Fig. 11b shows an example of this, where the left hand penetrates the head and the lower legs penetrate one another. Our network uses a fixed open hand pose, which may contribute to unnatural hand penetration errors. Self penetration of the 3D mesh body models does not occur 

CLEVER ET AL.: BODYPRESSURE - INFERRING BODY POSE AND CONTACT PRESSURE FROM A DEPTH IMAGE 

151 

frequently in the data because a mesh interpenetration term was used to create SLP-3Dfits, nor in the synthetic data because the physics simulations prevent it. Real human bodies have soft tissues that deform when in contact, which can be approximated as 3D model interpenetration, but the network outputs interpenetration that poorly matches soft tissue deformation. The problem is worsened by the frequent self-contact of limbs and body parts when a person rests. Our system also neglects pressure due to self contact and pressure differences due to the mass of one limb resting on another limb. Better accounting for the mechanics of self-contact might improve performance [29], [73], [74], [75], and reported height and weight data from Muller.€ et al. [75] may also be used to improve BetaNet. 

When using methods like ours, researchers and practitioners should carefully consider the specific populations of interest. How well our methods would perform with different populations remains an open question. For example, the networks we trained would be unlikely to perform well with children and amputees. Our trained networks and our evaluations of their performance have two notable dependencies. First, we used the publicly available SMPL model [2] trained with the CAESAR dataset [76], which consists of 3D scans of approximately 4,000 distinct body shapes. The CAESAR scans represent the body shapes of men and women aged 18-65 in the United States, the Netherlands, and Italy. As one would expect, this SMPL model is not intended to represent children, older adults, or people with medical conditions [77]. Second, we used the SLP dataset, which consists of data from 102 participants (28 female/74 male) recruited from undergraduate and graduate students at Northeastern University [3], [78]. Future research would benefit from more diverse populations. 

The GPU memory footprint of BPWnet is substantial. Reducing it may allow both Mod1 and Mod2 to be trained end-to-end, simplifying learning. Recent works in human body reconstruction provide other insights for boosting performance, including body-driven attention [79], structured prediction to explicitly model joint dependencies [80], joint occupancy estimation [81], and a method to combine keypoint- and parametric model- based human pose estimation methods [82]. 

## 9 CONCLUSION 

In summary, we presented a method to infer body pose and contact pressure from a depth image, which has the potential to automatically localize pressure injury risk areas using a consumer-grade depth camera. We described a method for annotating an existing human resting pose dataset with 3D body models, which we use for initializing a fast physics simulator and training and testing deep models. We generated a large synthetic resting pose dataset using physics simulations, which significantly boosts performance of our deep models. We introduced two deep learning models and compared their performance. The models were able to to accurately infer pose and contact pressure and outperform state-of-the-art methods for pose inference, even in the presence of visual occlusion from blankets. 

## ACKNOWLEDGMENTS 

The authors would like to thank Gerry Chen for his insightful feedback on the manuscript and Shuangjun Liu for assisting with the SLP dataset. 

## Disclosure 

Charles C. Kemp owns equity in and works for Hello Robot, a company commercializing robotic assistance technologies. Henry M. Clever is entitled to royalties derived from Hello Robot’s sale of products. 

## REFERENCES 

- [1] D. Berlowitz et al., “Preventing pressure ulcers in hospitals: A toolkit for improving quality of care,” Department of Health and Human Services, Agency for Healthcare Research and Quality, Accessed 2021. [Online]. Available: https://www.ahrq.gov/ sites/default/files/publications/files/putoolkit.pdf 

- [2] M. Loper, N. Mahmood, J. Romero, G. Pons-Moll , and M. J. Black, “SMPL: A skinned multi-person linear model,” ACM Trans. Graph., vol. 34, no. 6, pp. 248:1–248:16, 2015. 

- [3] S. Liu, X. Huang, N. Fu, C. Li, Z. Su, and S. Ostadabbas, “Simultaneously-collected multimodal lying pose dataset: Enabling in-bed human pose monitoring,” IEEE Trans. Pattern Anal. Mach. Intell., early access, Mar. 3, 2022, doi: 10.1109/TPAMI.2022.3155712. 

- [4] Y. Yin, J. P. Robinson, and Y. Fu, “Multimodal in-bed pose and shape estimation under the blankets,” 2020, arXiv:2012.06735. 

- [5] S. Song, F. Yu, A. Zeng, A. X. Chang, M. Savva, and T. Funkhouser, “Semantic scene completion from a single depth image,” in Proc. IEEE/CVF Conf. Comput. Vis. Pattern Recognit., 2017, pp. 1746–1754. 

- [6] Z. Luo et al., “Computer vision-based descriptive analytics of seniors’ daily activities for long-term health monitoring,” Mach. Learn. Healthcare, vol. 2, pp. 85:1–85:18, 2018. 

- [7] H. M. Clever, Z. Erickson, A. Kapusta, G. Turk, C. K. Liu, and C. C. Kemp, “Bodies at rest: 3D human pose and shape estimation from a pressure image using synthetic data,” in Proc. IEEE/CVF Conf. Comput. Vis. Pattern Recognit., 2020, pp. 6215–6224. 

- [8] O. Ronneberger, P. Fischer, and T. Brox, “U-Net: Convolutional networks for biomedical image segmentation,” in Proc. Int. Conf. Med. Image Comput. Comput.-Assisted Intervention, 2015, pp. 234–241. 

- [9] A. Bulat and G. Tzimiropoulos, “Human pose estimation via convolutional part heatmap regression,” in Proc. Eur. Conf. Comput. Vis., 2016, pp. 717–732. 

- [10] H. Rhodin, M. Salzmann, and P. Fua, “Unsupervised geometryaware representation for 3D human pose estimation,” in Proc. Eur. Conf. Comput. Vis., 2018, pp. 750–767. 

- [11] M. Oberweger, P. Wohlhart, and V. Lepetit, “Training a feedback loop for hand pose estimation,” in Proc. IEEE Int. Conf. Comput. Vis., 2015, pp. 3316–3324. 

- [12] S. Mansfield, K. Obraczka, and S. Roy, “Pressure injury prevention: A survey,” IEEE Rev. Biomed. Eng., vol. 13, pp. 352–368, 2019. 

- [13] M. Farshbaf, R. Yousefi, M. B. Pouyan, S. Ostadabbas, M. Nourani, and M. Pompeo, “Detecting high-risk regions for pressure ulcer risk assessment,” in Proc. Int. Conf. Bioinf. Biomed., 2013, pp. 255–260. 

- [14] J. J. Liu, M.-C. Huang, W. Xu, and M. Sarrafzadeh, “Bodypart localization for pressure ulcer prevention,” in Proc. Int. Conf. IEEE Eng. Med. Biol. Soc., 2014, pp. 766–769. 

- [15] M. B. Pouyan, J. Birjandtalab, M. Nourani, and M. M. Pompeo, “Automatic limb identification and sleeping parameters assessment for pressure ulcer prevention,” Comput. Biol. Med., vol. 75, pp. 98–108, 2016. 

- [16] R. Yousefi et al., “Bed posture classification for pressure ulcer prevention,” in Proc. Int. Conf. IEEE Eng. Med. Biol. Soc., 2011, pp. 7175–7178. 

- [17] S. Mansfield, S. Rangarajan, K. Obraczka, H. Lee, D. Young, and S. Roy, “Objective pressure injury risk assessment using a wearable pressure sensor,” in Proc. Int. Conf. Bioinf. Biomed., 2019, pp. 1561–1568. 

- [18] D. Pickham, N. Berte, M. Pihulic, A. Valdez, B. Mayer, and M. Desai, “Effect of a wearable patient sensor on care delivery for preventing pressure injuries in acutely ill adults: A pragmatic randomized clinical trial (LS-HAPI study),” Int. J. Nurs. Stud., vol. 80, pp. 12–19, 2018. 

IEEE TRANSACTIONS ON PATTERN ANALYSIS AND MACHINE INTELLIGENCE, VOL. 45, NO. 1, JANUARY 2023 

152 

- [19] K. Vanderwee, M. Clark, C. Dealey, L. Gunningberg, and T. Defloor, “Pressure ulcer prevalence in europe: A pilot study,” J. Eval. Clin. Pract., vol. 13, no. 2, pp. 227–235, 2007. 

- [20] N. A. Lahmann, R. J. Halfens, and T. Dassen, “Pressure ulcers in german nursing homes and acute care hospitals: Prevalence, frequency, and ulcer characteristics,” Ostomy Wound Manage., vol. 52, no. 2, 2006, Art. no. 20. 

- [21] O. Ghori et al., “Learning to forecast pedestrian intention from pose dynamics,” in Proc. Intell. Veh. Symp., 2018, pp. 1277–1284. 

- [22] F. Achilles, A.-E. Ichim, H. Coskun, F. Tombari, S. Noachtar, and N. Navab, “Patient MoCap: Human pose estimation under blanket occlusion for hospital monitoring applications,” in Proc. Int. Conf. Med. Image Comput. Comput.-Assisted Intervention, 2016, pp. 491–499. 

- [23] L. Casas, N. Navab, and S. Demirci, “Patient 3D body pose estimation from pressure imaging,” Int. J. Comput. Assist. Radiol. Surg., vol. 14, pp. 517–524, 2019. 

- [24] H. M. Clever, A. Kapusta, D. Park, Z. Erickson, Y. Chitalia, and C. C. Kemp, “3D human pose estimation on a configurable bed from a pressure image,” in Proc. IEEE/RSJ Int. Conf. Intell. Robots Syst., 2018, pp. 54–61. 

- [25] K. Chen et al., “Patient-specific pose estimation in clinical environments,” IEEE J. Transl. Eng. Health Med., vol. 6, pp. 1–11, 2018. 

- [26] S. Liu, Y. Yin, and S. Ostadabbas, “In-bed pose estimation: Deep learning with shallow dataset,” IEEE J. Transl. Eng. Health Med., vol. 7, pp. 1–12, 2019. 

- [27] S. Liu and S. Ostadabbas, “Seeing under the cover: A physics guided learning approach for in-bed pose estimation,” in Proc. Int. Conf. Med. Image Comput. Comput.-Assisted Intervention, 2019, pp. 236–245. 

- [28] Y.-W. Chao, J. Yang, W. Chen, and J. Deng, “Learning to sit: Synthesizing human-chair interactions via hierarchical control,” in Proc. AAAI Conf. Artif. Intell., 2021, pp. 5887–5895. 

- [29] M. Hassan, V. Choutas, D. Tzionas, and M. J. Black, “Resolving 3D human pose ambiguities with 3D scene constraints,” in Proc. Int. Conf. Comput. Vis., 2019, pp. 2282–2292. 

- [30] Y. Zhang, M. Hassan, H. Neumann, M. J. Black, and S. Tang, “Generating 3D people in scenes without people,” in Proc. IEEE/ CVF Conf. Comput. Vis. Pattern Recognit., 2020, pp. 6194–6204. 

- [31] J. Lee et al., “DART: Dynamic animation and robotics toolkit,” J. Open Source Softw., vol. 3, no. 22, 2018, Art. no. 500. 

- [32] J. Tan et al., “Sim-to-real: Learning agile locomotion for quadruped robots,” in Proc. Robot.: Sci. Syst., 2018, pp. 1–11. 

- [33] Z. Erickson, V. Gangaram, A. Kapusta, C. K. Liu, and C. C. Kemp, “Assistive gym: A physics simulation framework for assistive robotics,” in Proc. Int. Conf. Robot. Autom., 2020, pp. 10 169–10 176. 

- [34] Z. Erickson, H. M. Clever, G. Turk, C. K. Liu, and C. C. Kemp, “Deep haptic model predictive control for robot-assisted 

- [35] M.dressing,” inMacklin, Proc. Int. Conf. Robot. Autom.M. Muller,€ N. Chentanez, and, 2018, pp. 4437–4444.T.-Y. Kim, “Unified particle physics for real-time applications,” ACM Trans. Graph., vol. 33, no. 4, pp. 153:1–153:12, 2014. 

- [36] A. Clegg, W. Yu, Z. Erickson, J. Tan, C. K. Liu, and G. Turk, “Learning to navigate cloth using haptics,” in Proc. Int. Conf. Intell. Robots Syst., 2017, pp. 2799–2805. 

- [37] M. Cusumano-Towner, A. Singh, S. Miller, J. F. O’Brien, and P. Abbeel, “Bringing clothing into desired configurations with limited perception,” in Proc. Int. Conf. Robot. Autom., 2011, pp. 3983–3900. 

- [38] J. Matas, S. James, and A. J. Davison, “Sim-to-real reinforcement learning for deformable object manipulation,” in Proc. 2nd Conf. Robot Learn., 2018, pp. 734–743. 

- [39] S. Pirk et al., “Understanding and exploiting object interaction landscapes,” ACM Trans. Graph., vol. 36, no. 3, pp. 31:1–31:14, 2017. 

- [40] H. Wang et al., “Learning a generative model for multi-step human-object interactions from videos,” Comput. Graph. Forum, vol. 38, no. 2, pp. 367–378, 2019. 

- [41] W. Chen et al., “Synthesizing training images for boosting human 3D pose estimation,” in Proc. Int. Conf. 3D Vis., 2016, pp. 479–488. 

- [42] G. Varol et al., “Learning from synthetic humans,” in Proc. IEEE/ CVF Conf. Comput. Vis. Pattern Recognit., 2017, pp. 109–117. 

- [43] T. Yu et al., “SimulCap: Single-view human performance capture with cloth simulation,” in Proc. IEEE/CVF Conf. Comput. Vis. Pattern Recognit., 2019, pp. 5499–5509. 

- [44] J. Shotton et al., “Real-time human pose recognition in parts from single depth images,” in Proc. IEEE/CVF Conf. Comput. Vis. Pattern Recognit., 2011, pp. 1297–1304. 

- [45] A. Mart�ınez-Gonz�alez, M. Villamizar, O. Can�evet, and J.-M. Odobez, “Real-time convolutional networks for depth-based human pose estimation,” in Proc. Int. Conf. Intell. Robots Syst., 2018, pp. 41–47. 

- [46] Z. Zhong, L. Zheng, G. Kang, S. Li, and Y. Yang, “Random erasing data augmentation,” in Proc. AAAI Conf. Artif. Intell., 2020, pp. 13 001–13 008. 

- [47] B. Planche et al., “DepthSynth: Real-time realistic synthetic data generation from CAD models for 2.5D recognition,” in Proc. Int. Conf. 3D Vis., 2017, pp. 1–10. 

- [48] S. Zakharov, B. Planche, Z. Wu, A. Hutter, H. Kosch, and S. Ilic, “Keep it unreal: Bridging the realism gap for 2.5D recognition with geometry priors only,” in Proc. Int. Conf. 3D Vis., 2018, pp. 1–11. 

- [49] F. Bogo, A. Kanazawa, C. Lassner, P. Gehler, J. Romero, and M. J. Black, “Keep it SMPL: Automatic estimation of 3D human pose and shape from a single image,” in Proc. Eur. Conf. Comput. Vis., 2016, pp. 561–578. 

- [50] N. Kolotouros, G. Pavlakos, M. J. Black, and K. Daniilidis, “Learning to reconstruct 3D human pose and shape via model-fitting in the loop,” in Proc. IEEE/CVF Conf. Comput. Vis. Pattern Recognit., 2019, pp. 2252–2261. 

- [51] A. Kanazawa, M. J. Black, D. W. Jacobs, and J. Malik, “End-to-end recovery of human shape and pose,” in Proc. IEEE/CVF Conf. Comput. Vis. Pattern Recognit., 2018, pp. 7122–7131. 

- [52] G. Pavlakos, X. Zhou, K. G. Derpanis, and K. Daniilidis, “Coarseto-fine volumetric prediction for single-image 3D human pose,” in Proc. IEEE/CVF Conf. Comput. Vis. Pattern Recognit., 2017, pp. 7025–7034. 

- [53] N. Sarafianos, B. Boteanu, C. Ionescu, and I. A. Kakadiaris, “3D human pose estimation: A review of the literature and analysis of covariates,” Comput. Vis. Image Understanding, vol. 152, pp. 1–20, 2016. 

- [54] C. Zheng et al., “Deep learning-based human pose estimation: A survey,” 2020, arXiv:2012.13392. 

- [55] X. Zhou, X. Sun, W. Zhang, S. Liang, and Y. Wei, “Deep kinematic pose regression,” in Proc. Eur. Conf. Comput. Vis. Workshops, 2016, pp. 186–201. 

- [56] Y. Hasson et al., “Learning joint reconstruction of hands and manipulated objects,” in Proc. IEEE/CVF Conf. Comput. Vis. Pattern Recognit., 2019, pp. 11 807–11 816. 

- [57] P. Grady, C. Tang, C. D. Twigg, M. Vo, S. Brahmbhatt, and C. C. Kemp, “ContactOpt: Optimizing contact to improve grasps,” in Proc. IEEE/CVF Conf. Comput. Vis. Pattern Recognit., 2021, pp. 1471–1481. 

- [58] X. Zhou, M. Zhu, G. Pavlakos, S. Leonardos, K. G. Derpanis, and K. Daniilidis, “MonoCap: Monocular human motion capture using a CNN coupled with a geometric prior,” IEEE Trans. Pattern Anal. Mach. Intell., vol. 41, no. 4, pp. 901–914, Apr. 2019. 

- [59] A. Harouni, A. Karargyris, M. Negahdar, D. Beymer, and T. Syeda-Mahmood , “Universal multi-modal deep network for classification and segmentation of medical images,” in Proc. Int. Symp. Biomed. Imag., 2018, pp. 872–876. 

- [60] L. He, G. Wang, and Z. Hu, “Learning depth from single images with deep neural network embedding focal length,” IEEE Trans. Image Process., vol. 27, no. 9, pp. 4676–4689, Sep. 2018. 

- [61] H. Fan, H. Su, and L. J. Guibas, “A point set generation network for 3D object reconstruction from a single image,” in Proc. IEEE/ CVF Conf. Comput. Vis. Pattern Recognit., 2017, pp. 605–613. 

- [62] L. Ballan, A. Taneja, J. Gall, L. Van Gool, and M. Pollefeys, “Motion capture of hands in action using discriminative salient points,” in Proc. Eur. Conf. Comput. Vis., 2012, pp. 640–653. 

- [63] D. C. Boone and S. P. Azen, “Normal range of motion of joints in male subjects,” J. Bone Joint Surg., vol. 61, no. 5, pp. 756–759, 1979. 

- [64] A. Roaas and G. B. Andersson ., “Normal range of motion of the hip, knee and ankle joints in male subjects, 30–40 years of age,” Acta Orthopaedica Scandinavica, vol. 53, no. 2, pp. 205–208, 1982. 

- [65] J. M. Soucie et al., “Range of motion measurements: Reference values and a database for comparison studies,” Haemophilia, vol. 17, 

- [66] A. Tno. 3, pp. 500–507, 2011.ozeren,€ Human Body Dynamics: Classical Mechanics and Human Movement. Berlin, Germany: Springer, 1999. 

- [67] M. Matl, “Easy-to-use glTF 2.0-compliant OpenGL renderer for visualization of 3D scenes,” 2020. [Online]. Available: https:// github.com/mmatl/pyrender 

- [68] A. Ranjan, D. T. Hoffmann, D. Tzionas, S. Tang, J. Romero, and M. J. Black, “Learning multi-human optical flow,” Int. J. Comput. Vis., vol. 128, no. 4, pp. 873–890, 2020. 

CLEVER ET AL.: BODYPRESSURE - INFERRING BODY POSE AND CONTACT PRESSURE FROM A DEPTH IMAGE 

153 

- [69] J. Carreira, P. Agrawal, K. Fragkiadaki, and J. Malik, “Human pose estimation with iterative error feedback,” in Proc. IEEE/CVF Conf. Comput. Vis. Pattern Recognit., 2016, pp. 4733–4742. 

- [70] R. Liu et al., “An intriguing failing of convolutional neural networks and the coordconv solution,” in Proc. 32nd Int. Conf. Neural Inf. Process. Syst., 2018, pp. 9605–9616. 

- [71] D. P. Kingma and J. Ba, “Adam: A method for stochastic optimization,” 2014, arXiv:1412.6980. 

Patrick L. Grady received the BS degree in computer science and electrical and computer engineering from Duke University, Durham, North Carolina. He is currently working toward the PhD degree in robotics with the Georgia Institute of Technology, Atlanta, Georgia in the Healthcare Robotics Lab. He is interested in hand-object interaction and computer vision for robots. 

- [72] T. F. Runia, K. Gavrilyuk, C. G. Snoek, and A. W. Smeulders, “Cloth in the wind: A case study of physical measurement through simulation,” in Proc. IEEE/CVF Conf. Comput. Vis. Pattern Recognit., 2020, pp. 10 498–10 507. 

- [73] M. Fieraru, M. Zanfir, E. Oneata, A.-I. Popa, V. Olaru, and C. Sminchisescu, “Three-dimensional reconstruction of human interactions,” in Proc. IEEE/ CVF Conf. Comput. Vis. Pattern Recognit., 2020, pp. 7214–7223. 

- [74] M. Fieraru, M. Zanfir, E. Oneata, A. Popa, V. Olaru, and C. Sminchisescu, “Learning complex 3D human self-contact,” in Proc. AAAI Conf. Artif. Intell., 2021, pp. 1343–1351. 

- [75] L. Muller, A. A. Osman, S. Tang, C.-H. P. Huang, and M. J. Black,€ “On self-contact and human pose,” in Proc. IEEE/CVF Conf. Comput. Vis. Pattern Recognit., 2021, pp. 9990–9999. 

- [76] K. M. Robinette, S. Blackwell, H. Daanen, M. Boehmer, and S. Fleming, “Civilian american and european surface anthropometry resource (caesar), final report. Volume 1. Summary,” Sytronics Inc Dayton OH, USA, Tech. Rep. AFRL-HE-WP-TR-2002-0169, 2002. 

- [77] M. Black, personal communication via Email, Nov. 2021. 

Greg Turk received the PhD degree in computer science from the University of North Carolina at Chapel Hill, Chapel Hill, North Carolina, in 1992. He was a postdoctoral researcher with Stanford University, Stanford, California for two years. He is currently a professor with the Georgia Institute of Technology, Atlanta, Georgia, where he is a member of the School of Interactive Computing and the Graphics, Visualization and Usability a Eh au Center. His research interests include computer graphics, robotics, biological simulation and machine learning. He was the Technical Papers chair for ACM SIGGRAPH 2008. In 2012 he received the Computer Graphics Achievement Award from ACM SIGGRAPH for his computer graphics research. 

- [78] S. Ostadabbas, personal communication via Email, Nov. 2021. 

- [79] V. Choutas, G. Pavlakos, T. Bolkart, D. Tzionas, and M. J. Black, “Monocular expressive body regression through body-driven attention,” in Proc. Eur. Conf. Comput. Vis., 2020, pp. 20–40. 

- [80] E. Aksan, M. Kaufmann, and O. Hilliges, “Structured prediction helps 3D human motion modelling,” in Proc. IEEE/CVF Int. Conf. Comput. Vis., 2019, pp. 7144–7153. 

- [81] M. Mihajlovic, Y. Zhang, M. J. Black, and S. Tang, “LEAP: Learning articulated occupancy of people,” in Proc. Conf. Comput. Vis. Pattern Recognit., 2021, pp. 10 461–10 471. 

- [82] J. Li, C. Xu, Z. Chen, S. Bian, L. Yang, and C. Lu, “HybrIK: A hybrid analytical-neural inverse kinematics solution for 3D human pose and shape estimation,” in Proc. Conf. Comput. Vis. Pattern Recognit., 2021, pp. 3383–3393. 

Henry M. Clever received the BS degree in mechanical engineering from the University of Kansas, Lawrence, Kansas, and the MS degree in mechanical engineering from New York University, New York. He is currently working toward the PhD degree in robotics with the Georgia Institute of Technology, Atlanta, Georgia, in the Healthcare Robotics Lab. His research interests include robot understanding in unstructured environments, haptic and vision perception of humans and robots, humanrobot systems, physics simulation of humans and robots, and human pose estimation. 

Charles C. Kemp received the BS, MEng, and the PhD degrees from the Massachusetts Institute of Technology (MIT), Cambridge, Massachusetts in the areas of computer science and electrical engineering. He is currently an associate professor with Georgia Tech, Atlanta, Georgia in the Department of Biomedical Engineering with adjunct appointments with the School of Interactive Computing and the School of Electrical and Computer Engineering. In 2007, he founded the Healthcare Robotics Lab, which focuses on enabling robots to provide intelligent physical assistance in the context of healthcare. 

> " For more information on this or any other computing topic, please visit our Digital Library at www.computer.org/csdl. 

