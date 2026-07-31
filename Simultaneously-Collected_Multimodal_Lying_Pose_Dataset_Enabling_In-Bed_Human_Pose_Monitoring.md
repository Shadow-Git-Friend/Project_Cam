IEEE TRANSACTIONS ON PATTERN ANALYSIS AND MACHINE INTELLIGENCE, VOL. 45, NO. 1, JANUARY 2023 

1106 

## Simultaneously-Collected Multimodal Lying Pose Dataset: Enabling In-Bed Human Pose Monitoring 

Shuangjun Liu , Xiaofei Huang , Nihang Fu, Cheng Li, Zhongnan Su, and Sarah Ostadabbas 

Abstract—Computer vision field has achieved great success in interpreting semantic meanings from images, yet its algorithms can be brittle for tasks with adverse vision conditions and the ones suffering from data/label pair limitation. Among these tasks is in-bed human pose monitoring with significant value in many healthcare applications. In-bed pose monitoring in natural settings involves pose estimation in complete darkness or full occlusion. The lackof publiclyavailable in-bed pose datasets hinders the applicability of many successful human pose estimation algorithms for this task. In this paper, we introduce our Simultaneously-collected multimodal Lying Pose (SLP) dataset, which includes in-bed pose images from 109 participants captured using multiple imaging modalities including RGB, long wave infrared (LWIR), depth, and pressure map. We also present a physical hyper parameter tuning strategy for ground truth pose label generation under adverse vision conditions. The SLP design is compatible with the mainstream human pose datasets; therefore, the state-of-the-art 2D pose estimation models can be trained effectively with the SLP data with promising performance as high as 95% at PCKh@0.5 on a single modality. The pose estimation performance of these models can be further improved by including additional modalities through the proposed collaborative scheme. 

Index Terms—Human pose estimation, depth sensing, in-bed poses, multimodal data collection, pressure mapping, thermal imaging 

## Ç 

## 1 INTRODUCTION 

LEEP/AT-REST behavior monitoring is a critical aspect in Smany healthcare prediction, diagnostic, and treatment practices, in which accurately tracking poses that the person takes while in bed plays an important role in the outcomes of the studies in this field [1]. These studies reveal that in-bed poses affect the symptoms of many medical complications such as sleep apnea [2], pressure ulcers [3], and even carpal tunnel syndrome [4]. The need for automatic in-bed behavior monitoring systems is becoming more apparent especially during the recent COVID19 pandemic, when spiking numbers of patients require consistent monitoring throughout the day [5]. Medical system overload is also globally observed among the epicenters [6]. In such circumstances, automatic patient monitoring systems that can be employed unobtrusively at home or local medical centers not only could lead to reduced hospital visits and, therefore, mitigate the risk of infection spread, but they also could bring on significant workload relief for the already overworked caregivers. However, in-bed 

- The authors are with the Augmented Cognition Lab, Department of Electrical and Computer Engineering, Northeastern University, Boston, MA 02115 USA. E-mail: {shuliu, xhuang, nihang, ostadabbas}@ece.neu.edu, licheng968@gmail.com, zhongnan.su@outlook.com. 

Manuscript received 22 Aug. 2020; revised 12 Jan. 2022; accepted 27 Feb. 2022. Date of publication 3 Mar. 2022; date of current version 5 Dec. 2022. This work was supported by National Science Foundations under Grant NSFIIS 1755695. 

This work involved human subjects or animals in its research. Approval of all ethical and experimental procedures and protocols was granted by an institutional review board (IRB) approved by Northeastern University number IRB#17-06-04. 

(Corresponding author: Sarah Ostadabbas.) Recommended for acceptance by Y. A. Sheikh. Digital Object Identifier no. 10.1109/TPAMI.2022.3155712 

human pose monitoring systems still heavily rely on obtrusive wearable devices [7] or manually-taken reports from caregivers [8]. For one, the expensive medical-grade devices can hardly be offered beyond the professional hospital setting. Additionally, the behavioral reports are usually subjective and many even be contradictory among medical wards. 

The recent computer vision advancements in the human pose estimation topic have opened up a new avenue for contact-less patient monitoring tasks [9], [10]. However, the adverse vision conditions around in-bed human pose estimation such as the extreme illumination changes (including full darkness) and the presence of heavy occlusions (e.g., sheets or blanket) have hindered the state-of-the-art pose estimation algorithm accuracy for in-bed pose cases [11]. 

Nonetheless, given the importance of this topic in healthcare applications, in the last decade, a consistent effort has been made in order to address the in-bed pose estimation problem by employing other sensing modalities including pressure mapping systems [12], [13], depth sensing [14], as well as infrared imaging [15]. Yet the scale of data in these work are limited by having only a few participants, and none of the prior work has publicly released datasets to the machine learning/computer vision community. The lack of publicly available datasets not only makes it hard to reproduce the results and validate their effectiveness, but the comparison with newly-developed algorithms without a common benchmark has also not been possible in this field. 

To address the challenges surrounding the development of robust in-bed pose estimation algorithms, we present the firstever large-scale, publicly accessible in-bed human pose dataset, called Simultaneously-collected multimodal Lying Pose (SLP). The SLP includes all popular imaging modalities ever used in relevant mainstream in-bed pose estimation studies. 

0162-8828 © 2022 IEEE. Personal use is permitted, but republication/redistribution requires IEEE permission. See https://www.ieee.org/publications/rights/index.html for more information. Authorized licensed use limited to: Nazarbayev University. Downloaded on June 30,2026 at 07:52:32 UTC from IEEE Xplore.  Restrictions apply. 

LIU ET AL.: SIMULTANEOUSLY-COLLECTED MULTIMODAL LYING POSE DATASET: ENABLING IN-BED HUMAN POSE MONITORING 

1107 

In this paper, we focus on introducing the SLP dataset creation process and its underlying principles, its statistics, demo applications, and performance evaluation of state-of-the-arts human pose algorithms when trained/tested on the SLP. 

Potential impacts of SLP go beyond medical/healthcare applications. In the computer vision field, as a synchronized multimodal dataset, SLP provides the raw materials for human pose estimation studies with modalities beyond RGB or RGBD [16]. The four synchronized modalities in the SLP dataset can also facilitate related studies such as domain transfer or style translation between imaging modalities targeted for in-bed human pose estimation studies [17]. Moreover, although no motion capture data is provided as part the SLP dataset, 3D information is inherently inferrable via depth modality, which can potentially lead to models trained for in-bed 3D pose estimation. Finally, as computer vision field moves towards solving societal problems with high impact and great applicability, the specific context of SLP with its adverse vision condition cases can provide evaluation benchmarks for robustness and generalizability of the models yet to be developed. 

Fig. 1. Our Multimodal in-bed pose data collection setup, (a) in a regular bedroom, (b) in a simulated hospital room. 

## 2 RELATED WORK 

Our Contributions. this paper aims at serving not only the computer vision community but also the healthcare domain by making the following contributions: 

General Human Pose Estimation. There is a long track record of deep learning based human pose estimation algorithms since the introduction of convolutional pose machine [18]. These algorithms already achieved high performance for 2D human pose estimation [19], [20], which by now could even be deemed as a solved problem. As far as 3D human pose estimation, noticeable improvements have also been achieved either by the end-to-end training on real 3D human datasets [21] or based on a learned human body template [22]. Human pose estimation under more general settings has also been addressed such as in the wild [23] or for multi-person with camera distance awareness [24]. 

Presents a large-scale ( >100 subjects with nearly 15,000 pose images) human in-bed (i.e., at-rest) pose dataset, SLP, with multiple sensing modalities collected simultaneously including RGB, long wavelength infrared (LWIR), depth (D) and pressure map (PM). SLP can potentially serve as a benchmark for in-bed human behavior analysis studies based on different imaging modalities. 

SLP is formed in a compatible way with other mainstream human pose datasets; therefore, state-of-theart human pose estimation algorithms can effortlessly be trained on it and their performance can be reported in commonly-used pose estimation metrics. Addresses the difficulties for pose ground truth generation due to the lack of proper illumination and heavy occlusion by providing practical guidelines based on a novel physical hyperparameter tuning (PHPT) approach and its underlying reasoning. Presents a novel LWIR-D-PM visualization tool specific for in-bed pose monitoring by fusing multiple modalities, which provides an intuitive view for healthcare providers to investigate the physical state of the patient’s body during monitoring. 

Although more and more application settings have been explored in general for human pose estimation, only a few of them have focused on when a human is lying in a bed. The reason comes in multi-fold. First, the mainstream human pose estimation studies are based on the conventional RGB images which can hardly be effective under darkness, let alone when human subject is fully covered. Second, even for human annotators, pose ground truth generation under such contexts is very challenging and may not be feasible. While a great deal of effort towards detailed human pose annotation in a fine manner is proposed in [25], the annotation for fully covered cases still remains challenging. Lastly, due to the lack of available large-scale datasets, data-driven end-to-end approaches for in-bed human pose learning can barely be established. 

- In order to validate the SLP dataset diversity and broadness in terms of in-bed poses, besides evaluating the pose inference models on our main setting (a regular bedroom as shown in Fig. 1a), we specifically redeployed our system in a simulated hospital room (as shown in Fig. 1b) and collected extra data for this field test. The models trained on the main setting could transfer their learning into the new setting, which proves SLP versatility.[1] 

In-Bed Human Pose Estimation. RGB data has been employed for detecting “leaving” or “getting” into a bed [26], as well as general at-rest posture estimation [27]. However, the study settings in these methods are constrained to well illuminated environments and to cases with little to no occlusions. To address the adverse vision conditions in regard to the monitoring of the in-bed poses, other imaging modalities have been introduced, including pressure map, depth data, and our own recent work based on LWIR [15]. 

For pose estimation using pressure sensors/mats approaches, authors in [28] extracted binary signatures from pressure images obtained from a commercial pressure mat and used a binary pattern matching technique for pose 

> 1. The code is available at: https://github.com/ostadabbas/SLPFor pose estimation using pressure 

> Dataset-and-Codegithub.com/ostadabbas/SLP. The SLP dataset can be approaches, authors in [28] extracted binary downloaded at: https://web.northeastern.edu/ostadabbas/2019/06/ 27/multimodal-in-bed-pose-estimation/SLP Dataset for Multimodal from pressure images obtained from a commercial pressure In-Bed Pose Estimation. mat and used a binary pattern matching technique for pose Authorized licensed use limited to: Nazarbayev University. Downloaded on June 30,2026 at 07:52:32 UTC from IEEE Xplore.  Restrictions apply. 

IEEE TRANSACTIONS ON PATTERN ANALYSIS AND MACHINE INTELLIGENCE, VOL. 45, NO. 1, JANUARY 2023 

1108 

TABLE 1 

classification. The same group also introduced a Gaussian mixture model (GMM) clustering approach for concurrent pose classification and limb identification using pressure data [29]. In parallel, authors in [30] used pictorial structure model of the body based on both appearance and spatial information to localize the body parts within pressure images. Moreover, estimating 3D human pose directly from pressure map has been explored recently [31], [32]. However, the 2D or 3D pose ambiguity issues when body parts lose contact with the pressure sensors have been commonly observed in the relevant studies [31], [32]. Another factor that hinders the mainstream use of the pressure mapping systems is their high cost and difficulty in maintaining/ cleaning them, which limits their usage to the professional hospital rooms. 

SLP Dataset Compared to the State-of-the-Art 2D Human Pose Datasets 

||Human Pose<br>Dataset|RGB<br>Modality|Non-RGB<br>Modalities|Sample<br>Size|Pose<br>Types|Heavy<br>Occlusion|
|---|---|---|---|---|---|---|
||MPII [33]<br>LSP [34]<br>FLIC [35]<br>MS COCO [36]<br>SLP (Ours)|✓<br>✓<br>✓<br>✓<br>✓|✗<br>✗<br>✗<br>✗<br>✓|40K<br>12K<br>5003<br>250K<br>14.7K|Daily<br>Sports<br>Movies<br>Daily<br>In-bed|✗<br>✗<br>✗<br>✗<br>✓|



healthcare community who may seek a functional tool for in-bed human pose monitoring and actually face similar challenges in practice. Therefore, besides evaluating the effectiveness of our dataset in training 2D and testing 3D human pose estimation models, we also describe the technical aspects of the SLP dataset-forming process in detail, in case similar problems need to be solved from scratch in practice. Several state-of-the-art models trained on SLP will also be released to provide a handy tool to be employed directly for in-bed human pose monitoring purposes. 

Depth data has been extensively employed for estimating human poses during rest or sleep due to their invulnerability to the darkness during night time. Martinez et al. proposed a bed aligned map (BAM) descriptor based on depth information collected from a Microsoft Kinect camera to monitor the patient’s sleeping position (not the full pose) and body movements while in bed [14]. They also reported the estimation results for simulated covered cases, yet no real human data validation was given. Their followup work further added the recognition of high-level activities, such as removing bed covers, to their framework [37]. Yu et al. also employed the depth data to localize the head and body parts while lying in bed. However, their model is limited to the rough granularity only around torso and head parts [38]. 

## 3 INTRODUCING THE SLP DATASET 

To facilitate the ultimate goal of achieving a robust in-bed pose monitoring system, in the SLP dataset, we have incorporated high numbers of human subjects in various in-bed poses under extreme conditions such as complete darkness and fully covered cases. The SLP dataset therefore has the following characteristics: 

Other modalities such as near IR [11] and LWIR [15] have also been explored for in-bed pose estimation purposes. However, aside from our previous work [15], the datasets for other works are not publicly available, which makes it hard to reproduce their results and compare them with each other. Furthermore, these datasets are usually collected for specific application scenarios with limited modalities and annotations, which makes comparison across approaches and modalities even harder. 

(i) Modality Coverage. Mainstream imaging modalities for in-bed human pose are covered in the SLP including: RGB [27], LWIR [15], Depth [14] and PM [29]. 

(ii) Different Cover Conditions. Poses are collected under conditions as: no cover, a thin sheet with �1 mm thickness, and a thick blanket with �3 mm thickness. Some sample images in each modalities with different cover conditions are shown in Fig. 2. 

In this work, we aim at filling these gaps by publicly releasing an in-bed pose dataset, called SLP, which includes simultaneously-collected imaging modalities employed by the state-of-the-art studies for in-bed human pose estimation. The SLP dataset provides accurately labeled ground truth poses for each image even when it is taken under adverse vision conditions such as full darkness and/or complete occlusion. With the equivalent magnitude of samples to the well-known general purpose human pose datasets such as LSP [39] with 12 K human image samples, MPII [33] with 25 K samples, and LIP [40] with 50 K samples, using SLP makes training of the in-bed pose estimation models with deep neural network architecture from scratch possible. With public availability and versatile modalities, SLP can also be employed as a public benchmark for relevant studies. The multimodal nature of the SLP also allows the cross-domain collaboration and inference possible to overcome the issues specific to a single modality [31]. A comparison between the SLP and some popular state-ofthe-art 2D human pose datasets is shown in Table 1. 

(iii) Scenario Coverage. The most common application scenarios for in-bed pose estimation task are located in a bedroom or in a hospital room. Besides the main dataset, which is collected under a home setting (from 102 participants), we also collected a specific test set for a hospital room (from another 7 new participants) to test generalization of the selected pose estimation algorithms in the field. The statistics of the two settings are described in Table 2. The home setting is a simulated bedroom with a twin bed in the middle as shown in Fig. 1a. The hospital setting is collected in a simulated hospital room setting at Northeastern University Health Science Department as shown in Fig. 1b. 

(iv) Posture Coverage. Participants were asked to lie in natural poses evenly among supine, left, and right side sleep posture categories. For each category, 15 poses are collected under 3 cover conditions using 4 imaging modalities simultaneously. As fine-grained landmarks (such as face landmarks in COCO [36]) are hard to distinguish in non-RGB modalities, SLP annotation focuses on the major limbs and follows the joint definition of [34] with 14 joints in order as: Ankle-R, Knee-R, Hip-R, Hip-L, Knee-L, Ankle-L, Wrist-R, Elbow-R, Shoulder-R, Shoulder-L, Elbow-L, Wrist-L, Thorax, 

Our work not only aims at providing the raw materials to follows the joint definition of [34] with 14 joints in order as: the computer vision community under adverse vision conAnkle-R, Knee-R, Hip-R, Hip-L, Knee-L, Ankle-L, ditions with multimodal correspondence, but also to the Elbow-R, Shoulder-R, Shoulder-L, Elbow-L, Wrist-L, Thorax, Authorized licensed use limited to: Nazarbayev University. Downloaded on June 30,2026 at 07:52:32 UTC from IEEE Xplore.  Restrictions apply. 

LIU ET AL.: SIMULTANEOUSLY-COLLECTED MULTIMODAL LYING POSE DATASET: ENABLING IN-BED HUMAN POSE MONITORING 

1109 

TABLE 2 

SLP Dataset Composition 

||TABLE 2<br>SLP Dataset Composition|
|---|---|
|<4 <br>{|Environments<br>Males<br>Females<br>Subjects (train+test split)<br>Samples<br>Home<br>74<br>28<br>102 (90+12)<br>13770<br> ~~a~~<br> ~~a~~|
||Hospital<br>4<br>3<br>7 (0+7)<br>945|
||Total<br>78<br>31<br>109<br>14715|



**==> picture [190 x 12] intentionally omitted <==**

where, b[^] t is the estimated target pose, at and bt stand for the target appearance and pose, and ac and bc stand for the context appearance and pose, respectively. In our case, target means the subject of interest, the human body. The context includes the background and the object of non-interest such as the cover over the body. 

As mentioned in [15], the labeling error E depends on not only the pose terms but also the appearance terms. As all these parameters (i.e., fat; ac; bcg) can be decoupled from bt [41], they can be deemed as the hyperparameters of the function L. Therefore, we can formulate the pose estimation problem as an optimization problem 

**==> picture [212 x 21] intentionally omitted <==**

Fig. 2. SLP image data samples from in-bed supine and side postures: (a-f) show images captured using an RGB webcam, (g-l) show images captured using an LWIR camera, (m-r) shows images captured using a depth camera, and (s-x) shows images captured using a pressure mat. These images are taken from the participants without cover and with two different types (one thin and one thick) of covers. 

The estimated target pose, b[^] t is conditioned on other terms including at; ac; bc; Imod during the inference process. For example, human perception can achieve a more accurate b[^] t in well-illuminated RGB domain (IRGB) with no occlusion (bc; ac: no cover context), which means all these terms can be tuned to improve the inference. Unlike commonly referred hyperparameters in mathematical modeling, these variables are directly related to the actual physical properties of the object, which cannot be tuned freely, so we call them physical hyperparameters. Yet we showed that in our application, physical hyperparameters can also be altered effectively to optimize target L performance with prior knowledge. We employ LWIR annotation with RGB reference as an exemplar to demonstrate the PHPT guidelines for ground truth generation. As mappings between modalities are similar, these guidelines are generalizable to the other modality pairs. 

and Head Top, where L and R stand for the left and right side, respectively. 

(v) Additional Person-Specific Measurements. To facilitate future in-bed pose/behavior studies, especially when pressure sensing is involved, we also collected additional person-specific measures including the participants’ weight (kg), height (cm), gender (m/f), as well as tailor measurements (i.e., the circumference) of their bust, waist, hip, upper/lower arm, thigh, and shank (all in cm). The distribution of this data from all of the participants are shown in Fig. 6. With symmetric assumption, we only measured participants’ right side for paired limbs to simplify the process. 

Guideline I: Perform labeling under settings with the same bt but no cover to yield best pose labeling performance. Where, we inherently tune bc to improve the labeling process L. 

(vi) A Systematic Multimodal Ground Truth Generation. A physical hyperparameter tuning (PHPT) approach and its underlying reasoning are also presented. 

Guideline II: Employ IRGB counterpart as a heuristic guide to prune out false poses in ILWIR. We inherently tune Imod to improve L. For this guideline, one typical issue to address is that when human moves in the bed, the “heat residue” of the previous pose will result in misleading ghost temperature patterns, as the heated area needs time to diffuse heat gradually (see Fig. 3a), or when limbs are cuddled together, they may share similar temperature profiles (see Fig. 3b). All these will mislead the annotators during labeling. RGB reference can help to resolve these ambiguities. 

## 3.1 SLP Ground Truth Generation Guidelines 

Aiming at vision-based pose inference under adverse vision conditions (e.g., darkness, occlusion), the inference process is not only challenging for machine but also for human, which makes the ground truth generation difficult. To tackle this challenge, we use a physical hyperparameter tuning (PHPT) concept, first introduced in our previous work [15]. Here, we recast the concept and explain how our ground truth generation guidelines employ PHPT concept in practice. 

Guideline III: When finding exact joint locations are intractable in one domain, employ labels from another domain with bounded bias via homography mapping. We inherently tune Imod to improve L. For this guideline, one typical example is 

A pose labeling process can be defined as a function L that maps the image Imod in a modality mod 2 fRGB:LWRI; D;PMg to the target pose state bt, as 

Authorized licensed use limited to: Nazarbayev University. Downloaded on June 30,2026 at 07:52:32 UTC from IEEE Xplore.  Restrictions apply. 

IEEE TRANSACTIONS ON PATTERN ANALYSIS AND MACHINE INTELLIGENCE, VOL. 45, NO. 1, JANUARY 2023 

1110 

**==> picture [13 x 22] intentionally omitted <==**

**----- Start of picture text -----**<br>
(a)<br>**----- End of picture text -----**<br>


Fig. 3. Pose ambiguities in LWIR images with their corresponding RGB images, (a) false leg pose (in red) caused by the heat residue in the LWIR image,(b) false arm pose (in red) due to the cuddled limbs. The correct limb poses are given in green. 

Fig. 5. SLP cross domain alignment design: (a) alignment markers design, and (b) automatic center extraction in RGB imaging. 

that even when the general pose is known, the exact joint locations are still hard to allocate due to the blurred boundaries. Taking PM for example, the plausible pressure concentrated areas near feet are not actually the joint locations, while the heels and the arms are hard to locate from the PM map as shown in Fig. 4. Though homography mapping may result in ghost effect [42], in our application context, we argue such errors are bounded. The detailed discussion is provided in Appendix A, which can be found on the Computer Society Digital Library at http://doi.ieeecomputersociety.org/ 10.1109/TPAMI.2022.3155712. 

and pressure in PM. For example, IPM only depends on the contact pressure quantities no matter what RGB, LWIR, and D are. So we need to use combination of markers that trigger relevant responses in all modalities simultaneously. 

Based on this idea, the alignment marker is designed as shown in Fig. 5a. It consists of a cylinder jar that can easily be recognized by the RGB modality. A thermal plate is attached on top of the jar powered by the batteries in the chamber to alter the LWIR profile. Added weights inside the jar results in increased pressure profile. The jar height is around 10cm, which also alters the distance in the depth modality. To facilitate this alignment process and reduce experimenter’s workload, we designed an automatic center extraction algorithm by getting the geometric center of each marker’s contour. An extraction example in RGB domain is shown in Fig. 5b. 

## 3.2 Cross Modality Alignment 

Conventionally, a camera model can be calibrated with a checkerboard by estimating its intrinsic and extrinsic parameters [43]. Between well-calibrated camera systems, one point in one system can be accurately mapped into another if its depth is known. However, this approach cannot be used in our SLP dataset for cross modality mapping since: (1) except for the depth modality, depth is unknown in other SLP imaging modalities; (2) checkerboard will not provide thermal correspondence; and (3) pressure map does not have a pin hole model unlike other camera-based imaging systems. Instead, since all SLP modalities are in the form of 2D arrays, we employed homography for cross modality mapping [43] with respect to a plane parallel to the bed surface, and shared markers were used across modalities. 

## 4 DATASET COLLECTION AND EVALUATION 

## 4.1 SLP Data Collection Procedure 

All participants were from the Northeastern University student population that responded to our recruitment flyers. Using an institutional review boards (IRB)-approved protocol (IRB#17-06-04) at Northeastern University, we collected pose data from each participant while lying in a bed and randomly changing poses under three main categories of supine, left, and right side. A Cross modality alignment procedure was conducted before the main session. 

The SLP imaging process involves different modality functions, Imod 2 fIRGB; ILWIR; ID; IPMg, where each modality responds to a specific physical property, including visible light reflection in RGB, temperature in LWIR, distance in D, 

The whole process was managed by our central control software, which dispatches tasks to both participants and sensor devices to coordinate the human-machine collaboration. Each task is the combination of a pose and a cover condition, which requires a joint operation by sensors and human participants. A logical controller transformed tasks into audio guides to the experimenter and participant. At the start of each task, the participant was requested to move to another natural pose in the designated posture category and then the experimenter was instructed to alter the cover condition accordingly or relaunch the task in case of false operation. To synchronize the data collection module, a logical controller sent trigger command to drive relevant devices to capture and save data simultaneously to an external harddrive. This was implemented via a multi-thread mechanism 

Fig. 4. Demos of PM ground truth generation via physical hyperparameter tuning (PHPT) of guideline III in: (a) a supine pose, and (b) a right capture and save data simultaneously to an lying pose. Red dash line shows direct annotation, intuitively. drive. This was implemented via a multi-thread mechanism Authorized licensed use limited to: Nazarbayev University. Downloaded on June 30,2026 at 07:52:32 UTC from IEEE Xplore.  Restrictions apply. 

LIU ET AL.: SIMULTANEOUSLY-COLLECTED MULTIMODAL LYING POSE DATASET: ENABLING IN-BED HUMAN POSE MONITORING 

1111 

Fig. 6. Distribution of the measured person-specific parameters: (a) height (cm), (b) weight (kg), (c) tailor measurements (cm). 

in Python. The synchronization is accurate if the subject is holding a steady pose, i.e., the body limbs do not move fast enough to modify their location in the time difference that the device needs to spawn the different thread and perform all the image captures. 

## 4.2 Ground Truth Generation via PHPT 

To demonstrate our PHPT guidelines, we will illustrate this process with one modality LWIR, for example. We labeled the collected LWIR pose images by finding 14 body joints in each, based on three different strategies: (1) LWIR-G1 which employs only Guideline I, (2) LWIR-G3 which employs only Guideline III, and (3) LWIR-G123 which employs all three guidelines. As this is an evaluation of ground truth generation process, and there was no higher level standard to refer to, we used the labeling results of LWIR-G123 as the reference and evaluated how much other strategies are biased from this one using a normalized distance metric PCKh@0.5 [33]. 

The total differences between the labels from the golden standard (LWIR-G123) and the LWIR-G1 and LWIR-G3 are shown in Fig. 7 as the histograms of normalized distance error with fitted Gaussian curve. Compared to the LWIRG3, LWIR-G1 error shows lower mean value however larger variance, which demonstrates using LWIR-G1 yields high accuracy for recognizable poses yet has larger error for the ambiguous cases. In contrast, LWIR-G3 causes the ghosting errors that persist throughout the labeling process, but with less significant biases. To quantify the mapping error, suppose we purely employ the homography mapping (LWIRG3); in the worst case, the bias from the full guideline LWIR-G123 (mainly from direct labeling in LWIR) can be quantified by the error (normalized by the head size) with mean of 0.087 and STD of 0.042. 

## 4.3 In-Bed Pose Estimation Accuracy 

With the similar scale and annotation style of many publicly available human pose datasets, SLP is compatible for training of most of the state-of-the-art human pose estimation models (which are mainly RGB-based), in which their performance can be fairly evaluated with the well-recognized metrics employed in the computer vision field. 

Regarding the model architecture selection for in-bed pose estimation, we pursued the following rationale. The vision-based inference models targeted for human pose estimation, no matter using what imaging modalities (RGB or other modalities in the SLP dataset) follow the same logic, which is using the local and global evidence (patterns) present in the image to localize the body joints. One important aspect in this problem is in either RGB or other imaging modalities present in the SLP, the patterns are dependent on the underlying human pose. In other words, in an RGB image, the specific “limb” pattern shown in an area is caused by a specific pose that the subject holds. Inspired by this, the modalities we have in the SLP dataset also hold a causal effect to the underlying pose even under challenging conditions such as total darkness and full coverage. Namely, due to varied human poses, we can observe different heated patterns over the blanket in the LWIR modality, different elevated areas over the depth modality, and different pressure concentrations over the PM modality. Based on this logic, we can further believe that the existing state-of-the-art (SOTA) RGB-based pose estimation model architecture are capable of the pose inference tasks using the selected modalities in the SLP. 

Therefore, we trained several SOTA RGB-based pose inference models from scratch on the SLP dataset and reported their performance based on the PCKh metric in different imaging modalities, including: HRNet by Sun et al. (CVPR’19) [20], SimpleBaseLine by Xiao et al., (ECCV’18) [44], ChainedPredictions by Gkioxari et al. (ECCV’16) [45], PyraNet by Yang et al. (ICCV’17) [46], StackedHourGlass by Newell et al. (ECCV’16), PoseAttention by Chu et al. (CVPR’17) [47]. 

Implementation Details. In each work, we chose one of their typical configurations in our evaluation. In [20], we chose the W32 configuration with width 32 for the high resolution subset. In [44], we chose the configuration with ResNet-50 backbone. In [19], [46], [47], we set the stage number as 2. 

Fig. 7. Truncated histogram of normalized distance from the gold standard labels (using LWIR-G123) for labels generated using: (a) LWIR-G1, and (b) LWIR-G3. A Gaussian curve is fitted with green vertical lines as the mean and 3 standard deviation bounds. 

All models are adapted to work with the corresponding SLP modalities or combined modalities by varying the models’ input channels. For example, we modified the input channel number from three for RGB to one for modalities 

Authorized licensed use limited to: Nazarbayev University. Downloaded on June 30,2026 at 07:52:32 UTC from IEEE Xplore.  Restrictions apply. 

IEEE TRANSACTIONS ON PATTERN ANALYSIS AND MACHINE INTELLIGENCE, VOL. 45, NO. 1, JANUARY 2023 

1112 

Fig. 8. PCKh pose estimation performance of state-of-the-arts on LWIR, depth, and PM modalities under home setting. 

Fig. 9. Some qualitative results of in-bed pose estimation based on Sun, CVPR’19[20]. RGB images are given with the ground truth pose along side the inference results from depth, LWIR, and PM modalities. 

such as depth or IR. For multimodal cases, we concatenate the modality channels (three for RGB and one for each of the others). All models are trained from scratch with the corresponding modalities in the SLP, using the SLP training split, which is the first 90 subjects [15]. All models are trained on an NVIDIA V100 GPU with 100 epochs, learning rate 1e-3, Adam optimizer [48], learning decay rate 0.1 at epoch 70 and 90. Batch size is set to 30 for [46], [47], and 60 for other models to fit the GPU memory capacity. Our augmentation includes rotation, scaling, color jittering, as well as synthetic occlusion [49], to simulate the potential objects that may block the view-point, such as a bedside table. 

of 94.2%, 90.7%, 96.6% for LWIR, PM, and depth, respectively. [19] comes after it with a very similar performance. We believe the similarity between the results is due to the bed constraint, and the fact that human poses in bed seem to be relatively simpler than the general poses in daily activities. When provided with the informative visual clues from the imaging modalities in the SLP, most existing models clearly performs similarly well in in-bed pose estimation. 

[46] and [19] share similar network structure, where the feature merging only considers the neighboring scales. In comparison, the [20] merges the feature maps from all scales for each level, which is more effective for difficult poses, difficult view angles, and complicated visual patterns in RGB domain and show the best performance in public benchmarks. Such design may avoid the fake positive joints but at the same time it may sacrifice some localization accuracy by always combining the features from higher scale maps. Some qualitative results from Sun et al. model [20] are shown in Fig. 9, where we added the RGB pose image counterparts with the ground truth for easy observation, followed by inference result from other modalities. 

Evaluations Under the Home Setting. The models’ pose estimation performance based on each modality is reported in Fig. 8. Overall, pose estimation using LWIR or depth modality shows noticeably higher performance than PM modality, which complies with the findings in other PM based studies due to the ambiguity issues when limbs have no contact with the bed [31], [32]. Depth-based inference shows more stable performance compared to LWIR, with all 6 methods having over 90% at PCKh@0.5 against only 4 methods when LWIR is used. In our test, [46] comes out to have the best performance across all modalities with highest PCKh@0.5 

Furthermore, we compared these models’ performance (in PCKh@0.5 metric) when trained and tested on MPII 

Authorized licensed use limited to: Nazarbayev University. Downloaded on June 30,2026 at 07:52:32 UTC from IEEE Xplore.  Restrictions apply. 

LIU ET AL.: SIMULTANEOUSLY-COLLECTED MULTIMODAL LYING POSE DATASET: ENABLING IN-BED HUMAN POSE MONITORING 

1113 

TABLE 3 

PCKh@0.5 Performance, When State-of-the-Art Models are Trained on MPII [33] (All in RGB Modality) and SLP (Its Individual LWIR, PM, and Depth Modalities) Datasets and Tested on Corresponding Dataset/Modality, Respectively 

|Datasets||SLP|MPII|
|---|---|---|---|
|Modalities|LWIR<br>c0<br>c1<br>c2<br>total|PM<br>c0<br>c1<br>c2<br>total|Depth<br>RGB<br>c0<br>c1<br>c2<br>total<br>total|
|Sunet al.[20]<br>Xiaoet al.[44]<br>Gkioxariet al.[45]<br>Chuet al.[47]<br>Yanget al.[46]<br>Newellet al.[19]|95.2<br>93.1<br>91.9<br>93.4<br>94.2<br>92.0<br>91.4<br>92.5<br>90.4<br>88.7<br>87.2<br>88.8<br>91.6<br>89.3<br>88.8<br>89.9<br>96.0<br>93.6<br>93.0<br>94.2<br>95.8<br>93.5<br>92.6<br>94.0|84.4<br>84.3<br>84.2<br>84.3<br>86.5<br>87.1<br>86.8<br>86.8<br>88.5<br>88.6<br>88.4<br>88.5<br>87.9<br>88.2<br>88.2<br>88.1<br>90.5<br>90.7<br>90.7<br>90.7<br>90.1<br>90.0<br>90.2<br>90.1|97.7<br>95.8<br>95.6<br>96.4<br>92.3<br>96.9<br>94.5<br>94.6<br>95.3<br>91.5<br>95.8<br>93.3<br>93.4<br>94.2<br>85.3<br>96.8<br>93.3<br>93.6<br>94.6<br>91.5<br>97.9<br>96.1<br>95.9<br>96.7<br>92.0<br>97.6<br>96.1<br>95.8<br>96.5<br>90.9|



Where, c0 stands for no cover, c1 stands for the thin sheet and c2 stands for the thick blanket. 

TABLE 4 

Mean and Variance of Two Human Pose Estimation Models Trained/Tested on MPII [33], COCO [36], and SLP Datasets 

|Models|Datasets|MPII|COCO|SLP-LWIR|SLP-PM|SLP-Depth|
|---|---|---|---|---|---|---|
|Sunet al.[20]|Mean<br>STD|0.167<br>0.127|0.167<br>0.136|0.172<br>0.107|0.214<br>0.117|0.157<br>0.099|
|Xiaoet al.[44]|Mean<br>STD|0.173<br>0.127|0.349<br>0.118|0.177<br>0.107|0.206<br>0.115|0.163<br>0.101|



The reported performance is based on the PCKh@0.5 metric. 

dataset as a general purpose human pose dataset [33], and when trained and tested on the SLP dataset, as provided in Table 3. Except the PM, all these pose inference models show comparable pose estimation performance when trained on SLP images in LWIR and depth modalities, compared to the RGB pose images. 

capability to train large-scale networks from scratch in the context for the in-bed human pose estimation problem. 

When the pre-trained models are deployed in a new environment, one major concern is the domain shift issue. However, this issue did not lead to a significant performance drop in our case. We argue that the non-RGB modalities selected in the SLP are less affected from the environment change under our specific application context. Namely, RGB data is significantly affected by the subject’s appearance and the environment’s illumination, and the image data can differ dramatically from each other even in similar poses. However, the non-RGB modalities in the SLP are less affected by these variations. 

Table 3 shows that having covers brings negative effect on models’ performance for LWIR, yet no significant performance drops are observed among PM cases. These results agree with the modalities’ characteristics that covers especially thick ones will significantly affect the pattern generated in LWIR modality, while PM is based on the contact pressure and is less affected by the cover conditions. In the depth modality, while covers will affect the pose patterns, yet their thickness shows not much differences since it is negligible compared to the depth sensing range. 

Ablation Study. Different from model-focused works, our ablation study focuses on how SLP modalities influence the pose estimation results by extensive evaluation of individual modalities (LWIR, depth, or PM) and their possible collaborations by concatenating corresponding modalities as additional input channels. For this evaluation, we chose Sun et al. [20] and Xiao et al. [44] pose estimation models and their estimation results for individual joints and overall are shown in Fig. 11 for [20] and in Appendix C, available in the online supplemental material for [44], respectively. 

Field Test Under the Hospital Setting. In the hospital setual modalities (LWIR, depth, or PM) and their possible colting, our system was deployed in a simulated hospital room laborations by concatenating corresponding involving different contexts such as: different ceiling height, additional input channels. For this evaluation, we chose Sun different bed (a commercial Hill-Rom hospital bed), sheets/ et al. [20] and Xiao et al. [44] pose estimation blankets from different brands/colors, and new particitheir estimation results for individual joints and pants. This reflects most of the possible changes that could shown in Fig. 11 for [20] and in Appendix C, occur when our approach is employed in a real application the online supplemental material for [44], respectively. scenario. We collected pose data from all modalities (except According to their performance, in single PM) from 7 subjects and tested the performance of our preLWIR and depth are more effective for pose estimation than trained pose estimation models against this new dataset. PM. However, by collaborating with either LWIR Their results are shown on Fig. 10. The figure shows that PM performance can be significantly improved as shown in the majority of the models trained on SLP demonstrate a PM-LWIR and PM-depth subplots. Fig. 11 reveals that PM is robust performance in this field test and [19] for LWIR not counterproductive for inference and could be 96.5% and [20] for depth 96.1%, in PCKh@0.5 come out to be mentary to other modalities, as reflected in the best performers. In these tests, both [19] and [46] show a PM-depth subplots, where both show performance improverobust performance in both the original set test and the field ment over their single modality counterparts. test, where [46] is a revised version of [19] with additional The underlying reason could be attention mechanism. From these results, especially combininspecting the qualitative results in Fig. 9. For ing our specific field test in a hospital setting, SLP shows the second row of Fig. 9 shows that the PM can hardly estimate Authorized licensed use limited to: Nazarbayev University. Downloaded on June 30,2026 at 07:52:32 UTC from IEEE Xplore.  Restrictions apply. 

According to their performance, in single modality test, LWIR and depth are more effective for pose estimation than PM. However, by collaborating with either LWIR or depth, PM performance can be significantly improved as shown in PM-LWIR and PM-depth subplots. Fig. 11 reveals that PM is not counterproductive for inference and could be complementary to other modalities, as reflected in PM-LWIR and PM-depth subplots, where both show performance improvement over their single modality counterparts. 

The underlying reason could be comprehended by inspecting the qualitative results in Fig. 9. For example, the second row of Fig. 9 shows that the PM can hardly estimate 

IEEE TRANSACTIONS ON PATTERN ANALYSIS AND MACHINE INTELLIGENCE, VOL. 45, NO. 1, JANUARY 2023 

1114 

**==> picture [198 x 143] intentionally omitted <==**

**==> picture [198 x 145] intentionally omitted <==**

Fig. 10. PCKh pose estimation performance of state-of-the-arts on LWIR and depth modalities under hospital setting. 

**==> picture [506 x 218] intentionally omitted <==**

Fig. 11. PCKh pose estimation performance of [20] using images in LWIR, depth, and PM modality and their combinations. 

the arms that are out of contact with the bed, while LWIR and depth can localize both arms more accurately. On the contrary, in the first row of Fig. 9, when the head rests on the right arm, the depth modality fails to infer the pose of the arm correctly due to the blocked view, while it is clearly presented in PM. These examples show the complementary effect of PM on LWIR and depth modalities for pose estimation. Furthermore, in PM modality, the better performed joint localization are more likely to happen around supportive area such as hips, shoulders, and heels. An interesting fact is that these areas are all high risk areas for developing pressure ulcers or bedsore as discussed in relevant studies [50]. 

the original MPII training set. We then compared the official release of these model with the SLP fine-tuned versions head-to-head over three test sets, including SLP home setting, SLP hospital setting, and MPII test set, respectively, as shown in Table 5. 

These results demonstrate that although the pre-trained models show a reasonable performance over the no cover cases (c0), their performance drops significantly in covered cases (c1, c2, total). This is somehow expected, as the MPII human pose dataset does not contain many blanket covered samples and pose annotations to let the models learn. The SLP fine-tuned versions show significant improvement over the SLP dataset (in both home and hospital setting). At the same time, compared to their official performance over the MPII, the SLP fine-tuned versions still show equivalent performance or even slightly better performance. We made the following observations based on this experiment: (1) Impressive performance of models after being fine-tuned on SLP over covered cases in the RGB modality.. Although covered poses in RGB images seem to be hard to recognize by the human eye, there seem to be enough subtle clues for machine intelligence. Taking a closer look at the SLP RGB images, we may notice that even for covered subjects, there are subtle 

## 5 THE EFFECT OF GROUND TRUTH SUPERVISION IN OCCLUDED RGB IMAGES 

Although RGB modalities do not work in total darkness, it following observations based on this experiment: (1) Impresis interesting to investigate whether or not supervising the sive performance of models after being fine-tuned on SLP over covRGB-based models by the underlying ground truth pose ered cases in the RGB modality.. Although covered makes them capable of recognizing heavily occluded limbs. RGB images seem to be hard to recognize by the To test this hypothesis, we employed two SOTA models eye, there seem to be enough subtle clues for machine intel(Sun et al. [20], and Xiao et al. [44]) and fine-tuned them on ligence. Taking a closer look at the SLP RGB the SLP dataset (training portion of the home setting) plus may notice that even for covered subjects, there Authorized licensed use limited to: Nazarbayev University. Downloaded on June 30,2026 at 07:52:32 UTC from IEEE Xplore.  Restrictions apply. 

LIU ET AL.: SIMULTANEOUSLY-COLLECTED MULTIMODAL LYING POSE DATASET: ENABLING IN-BED HUMAN POSE MONITORING 

1115 

TABLE 5 

PCKh@0.5 Performance of the State-of-the-Art Pose Estimation Models Tested on Test-Portion of the MPII and SLP Datasets 

|Test Datasets||SLP@home settin|SLP@home setting|||SLP@hospital setting|SLP@hospital setting||MPII|
|---|---|---|---|---|---|---|---|---|---|
|Cover Conditions|c0|c1|c2|total|c0|c1|c2|total|total|
|Sunet al.[20] (original)|82.7|28.2|28.5|46.5|93|38.6|35.5|55.7|90.3|
|Sunet al.[20] (fine-tuned on SLP)|97.8|94.6|92.5|94.9|98.4|94.8|81.6|91.6|90.3|
|Xiaoet al.[44] (original)|80.9|26.1|29.9|45.6|92.1|33.1|30|51.7|89.1|
|Xiaoet al.[44] (fine-tuned on SLP)|97.8|95|92.5|95.1|98.9|98|85.8|93.2|89.2|



The SOTA are compared as (1) their official release, and (2) their fine-tuned versions based on SLP home setting and MPII datasets. c0 stands for no cover, c1 stands for the thin sheet, and c2 stands for the thick blanket. Please note that all of the experiments on SLP in this table are using only RGB modality. 

wrinkles and shadow changes over the blanket that are caused by the limb-occupied areas. This may not be significant for human eyes; however via extensive training, the models could capture these subtle clues to give accurate predictions. (2) No significant improvements after fine-tuning when tested on the MPII dataset. SLP provides large quantities of covered cases; however, it does not help to improve models’ performance over the general dataset of MPII. This is because the occlusion (covered cases) provided in the SLP is very specific to the in-bed poses, which is a blanket over a human in the bed. Under this context, occluded areas show slight clues, as mentioned in (1). However, this does not hold in most of the MPII occlusion cases, where the subjects are usually occluded by independent entities without contact, such as a foreground human or a piece of furniture. In this case, there is no longer any causal effect of the target pose and the pattern over the occluded areas. 

pose visualization tool that combines LWIR, depth and PM modality images and visualizes them simultaneously, as shown in Fig. 12. As all modalities of SLP are collected with correspondence, this presentation can be effortlessly generated by rendering the coupling modalities one by one. Fig. 12 shows examples with multiple cover conditions from two general in-bed posture categories. A typical benefit of this LWIR-D-PM visualization could be for relevant medical studies–for example, to investigate which lying poses will lead to high pressure concentration areas and therefore be a high risk area for bedsore development [51]. 

## 5.2 Exploring 3D In-Bed Pose Estimation 

Since in-bed poses suppose to be simpler compared to the public datasets for general purpose, if the darkness and occlusion are the major hinder to SOTA models’ performance, it is plausible that SOTAs are able to predict in-bed poses if the unoccluded RGB is provided. Given the high interest in the 3D human pose estimation topic, we tested several state-of-the-art 3D human pose estimation models based on RGB including Ronchi et al. (BMVC’17) [52], Zhou et al. (ICCV’17) [53], Moon et al. (ICCV’19) [54], and based on depth including Xiong et al. (ICCV’19) [55], by feeding them pose images in the corresponding modalities (only cases with no cover). Some qualitative results are shown in Fig. 13. The results in the last column of Fig. 13 show that the depth based pre-trained model of [55] fails most of the time. The reasons for this may come from (1) the body parts are blended into each other due to the rest state of in-bed human as shown in Fig. 12, (2) the bed surface is tightly attached to the body which is misleading. This is not usually an issue in the existing depth-based human datasets such as Invariant Top View (ITOP) dataset [56] for daily activities. 

Overall, Table 5 shows that SLP will not improve the models’ performance over a human pose dataset for daily activities, while it significantly improves their performance over occluded in-bed human cases without hurting original performance. From this aspect, SLP is helpful to enhance a pose estimation model’s capability by extending its application scope to in-bed poses. 

## 5.1 LWIR-D-PM Visualization 

Our SLP ground truth generation study revealed that human annotators can hardly recognize the poses that are taken in full darkness or high occlusion, only based on the RGB images (look at second and third rows of Fig. 9). This would be the same for the healthcare providers in sleep behavior monitoring practices. Furthermore, information such as a person’s body geometry, its temperature and its contact pressure with the bed cannot be extracted from the RGB modality alone. Therefore, we have developed a multimodal 

On the RGB side, most models can roughly localize the correct human joints. This complies with our assumption that in-bed human appearances come from the similar distribution as the ones in general human pose datasets. However, for individual limbs/joints, the estimation inaccuracy exists when carefully look at Fig. 13, especially when the subject rest in an “in-bed” specific pose such as resting the head on the arms Fig. 13 row 1 or rest with bent legs row 2. One major issues comes from the depth uncertainty. For example, from the perspective of daily activity, it is plausible to assume the subject is stretching the leg back to kick something. It actually suggests that SOTA pose estimators for general purpose are not necessarily effective given a specific context such as in-bed human. SLP indeed provides 

> Fig. 12. A demo of the LWIR-D-PM visualization tool. cific context such as in-bed human. SLP indeed Authorized licensed use limited to: Nazarbayev University. Downloaded on June 30,2026 at 07:52:32 UTC from IEEE Xplore.  Restrictions apply. 

IEEE TRANSACTIONS ON PATTERN ANALYSIS AND MACHINE INTELLIGENCE, VOL. 45, NO. 1, JANUARY 2023 

1116 

their having different pose distribution from the common daily activities [27]. So although the SLP dataset is supposed to show an easier pose manifold, complex scenarios (such as doctors showing up next to the patient) could reduce the models’ accuracy during inference. 

We argue that SLP potential values are not limited to the working examples presented in this paper. In the computer vision field, SLP presents an exemplar recognition/regress problem under adverse vision conditions, which can be a good starting point for studying similar problems when RGB is no longer effective or available. Furthermore, its multimodal nature with correspondence makes the SLP dataset a qualified candidate for domain adaptation and transfer learning studies for in-bed body pose estimation. In the healthcare field, pre-trained pose estimation models on SLP can provide a handy toolkit to track patient poses while in bed. Reliable yet automatic human pose estimation can provide the foundation for many higher level studies such as patient action recognition or behavior monitoring. We would like to leave these suggestions as open topics for ; future studies in which SLP can serve the community. 

E; 

## REFERENCES 

   - [1] A. M. Neill, S. M. Angus, D. Sajkov, and R. D. McEVOY, “Effects of sleep posture on upper airway stability in patients with obstructive sleep apnea,” Amer. J. Respir. Crit. Care Med., vol. 155, no. 1, pp. 199–204, 1997. 

- A 

   - [2] C. H. Lee, D. K. Kim, S. Y. Kim, C.-S. Rhee, and T.-B. Won, “Changes in site of obstruction in obstructive sleep apnea patients according to sleep position: A dise study,” The Laryngoscope, vol. 125, no. 1, pp. 248–254, 2015. 

Fig. 13. Qualitative results of 3D in-bed pose estimation. RGB images with ground truth are given followed by 3D pose estimation results from Ronchi et al. (BMVC’17) [52], Zhou et al. (ICCV’17) [53], Moon et al. (ICCV’19) [54], and Xiong et al. (ICCV’19) [55]. 

- [3] S. Ostadabbas, R. Yousefi, M. Nourani, M. Faezipour, L. Tamil, and M. Q. Pompeo, “A resource-efficient planning for pressure ulcer prevention,” IEEE Trans. Informat. Technol. Biomed., vol. 16, no. 6, pp. 1265–1273, Nov. 2012. 

- [4] S. J. McCabe and Y. Xue, “Evaluation of sleep position as a potential cause of carpal tunnel syndrome: Preferred sleep position on the side is associated with age and gender,” Hand, vol. 5, no. 4, pp. 361–363, 2010. 

complementary pose data to existing benchmarks and can be further explored. 

- [5] C. D. (COVID-19), 2018. [Online]. Available: https://www.cdc. gov/coronavirus/2019-ncov/cases-updates/cases-in-us.html, 

## 6 CONCLUSION 

- [6] A. Haleem, M. Javaid, and R. Vaishya, “Effects of COVID 19 pandemic in daily life,” Curr. Med. Res. Pract., vol. 10, no. 2, pp. 78–79, 2020. 

In this work, we introduce the first-ever large-scale in-bed pose dataset, called SLP that includes in-bed pose images simultaneously-collected from four imaging modalities including RGB, depth, long wavelength IR (LWIR), and pressure map. The SLP dataset provides accurately labeled ground truth poses for each image even when it is taken under adverse vision conditions such as full darkness and/ or complete occlusion. The SLP dataset effectiveness is illustrated in our evaluation experiments when multiple stateof-the-art human pose estimation models exhibited robust performance across different modalities, varying cover conditions, and home versus hospital environments. 

- [7] J. LaBuzetta, J. Hermiz, V. Gilja, and N. Karanjia, “Using accelerometers in the neurological ICU to monitor unilaterally motor impaired patients (P3. 204),” Neurology, vol. 86, 2016. 

- [8] D. M. Smith, “Pressure ulcers in the nursing home,” Ann. Intern. Med., vol. 123, no. 6, pp. 433–438, 1995. 

- [9] J. Yuan, Z. Liu, and Y. Wu, “Discriminative video pattern search for efficient action detection,” IEEE Trans. Pattern Anal. Mach. Intell., vol. 33, no. 9, pp. 1728–1743, Sep. 2011. 

- [10] B. Rezaei et al., “Target-specific action classification for automated assessment of human motor behavior from video,” Sensors, vol. 19, no. 19, 2019, Art. no. 4266. 

- [11] S. Liu, Y. Yin, and S. Ostadabbas, “In-bed pose estimation: Deep learning with shallow dataset,” IEEE J. Transl. Eng. Health Med., vol. 7, pp. 1–12, 2019. 

In-bed pose cases are very rare in the existing pose datasets. The publicly-available human pose datasets such as MPII [33], COCO [36], LSP [34], and FLIC [35] are predominantly from scenes such as sports, TV shows, and other daily activities, and none provides any specific in-bed poses. Besides privacy issues which have hampered the large-scale data collection, in-bed pose images differ from available pose datasets due to the notable differences in lighting conditions throughout a day (with no light during sleep time), people being covered with sheet or blanket during sleep, and 

- [12] J. J. Liu et al., “A dense pressure sensitive bedsheet design for unobtrusive sleep posture monitoring,” in Proc. IEEE Int. Conf. Pervasive Comput. Commun., 2013, pp. 207–215. 

- [13] S. Ostadabbas, M. B. Pouyan, M. Nourani, and N. Kehtarnavaz, “In-bed posture classification and limb identification,” in Proc. IEEE Biomed. Circuits Syst. Conf. Proc., 2014, pp. 133–136. 

- [14] M. Martinez, B. Schauerte, and R. Stiefelhagen, “BAM depthbased body analysis in critical care,” in Proc. Int. Conf. Comput. Anal. Images Patterns, 2013, pp. 465–472. 

- [15] S. Liu and S. Ostadabbas, “Seeing under the cover: A physics guided learning approach for in-bed pose estimation,” in Proc. Int. Conf. Med. Image Comput. Comput.-Assist. Intervention, 2019, pp. 236–245. 

Authorized licensed use limited to: Nazarbayev University. Downloaded on June 30,2026 at 07:52:32 UTC from IEEE Xplore.  Restrictions apply. 

LIU ET AL.: SIMULTANEOUSLY-COLLECTED MULTIMODAL LYING POSE DATASET: ENABLING IN-BED HUMAN POSE MONITORING 

1117 

- [16] F. Ofli, R. Chaudhry, G. Kurillo, R. Vidal, and R. Bajcsy, “Berkeley mhad: A comprehensive multimodal human action database,” in Proc. IEEE Workshop Appl. Comput. Vis., 2013, pp. 53–60. 

- [17] P. Isola, J.-Y. Zhu, T. Zhou, and A. A. Efros, “Image-to-image translation with conditional adversarial networks,” in Proc. IEEE Conf. Comput. Vis. Pattern Recognit., 2017, pp. 5967–5976. 

- [18] S.-E. Wei, V. Ramakrishna, T. Kanade, and Y. Sheikh, “Convolutional pose machines,” Proc. IEEE Conf. Comput. Vis. Pattern Recognit., 2016, pp. 4724–4732. 

- [19] A. Newell, K. Yang, and J. Deng, “Stacked hourglass networks for human pose estimation,” Proc. Eur. Conf. Comput. Vis., 2016, pp. 483–499. 

- [20] K. Sun, B. Xiao, D. Liu, and J. Wang, “Deep high-resolution representation learning for human pose estimation,” in Proc. IEEE/CVF Conf. Comput. Vis. Pattern Recognition, 2019, pp. 5686–5696. 

- [21] C. Ionescu, D. Papava, V. Olaru, and C. Sminchisescu, “Human3.6M: Large scale datasets and predictive methods for 3D human sensing in natural environments,” IEEE Trans. Pattern Anal. Mach. Intell., vol. 36, no. 7, pp. 1325–1339, Jul. 2014. 

- [22] F. Bogo, A. Kanazawa, C. Lassner, P. Gehler, J. Romero, and M. J. Black, “Keep it SMPL: Automatic estimation of 3D human pose and shape from a single image,” in Proc. Eur. Conf. Comput. Vis., 2016, pp. 561–578. 

- [23] X. Zhou, Q. Huang, X. Sun, X. Xue, and Y. Wei, “Towards 3D human pose estimation in the wild: A weakly-supervised approach,” in Proc. IEEE Int. Conf. Comput. Vis., 2017, pp. 398–407. 

- [24] G. Moon, J. Y. Chang, and K. M. Lee, “Camera distance-aware top-down approach for 3D multi-person pose estimation from a single RGB image,” in Proc. IEEE Int. Conf. Comput. Vis., 2019, pp. 10132–10141. 

- [25] C. Lassner, J. Romero, M. Kiefel, F. Bogo, M. J. Black, and P. V. Gehler, “Unite the people: Closing the loop between 3D and 2D human representations,” in Proc. IEEE Conf. Comput. Vis. Pattern Recognit., 2017, pp. 4704–4713. 

- [26] J.-R. Ding, “Bed status detection for elder-care center,” in Proc. 16th Int. Conf. Syst., Signals Image Process., 2009, pp. 1–4. 

- [27] S. Liu and S. Ostadabbas, “A vision-based system for in-bed posture tracking,” in Proc. IEEE Int. Conf. Comput. Vis., 2017, pp. 1373–1382. 

- [28] M. B. Pouyan, S. Ostadabbas, M. Farshbaf, R. Yousefi, M. Nourani, and M. Pompeo, “Continuous eight-posture classification for bedbound patients,” in Proc. 6th Int. Conf. Biomed. Eng. Inform., 2013, pp. 121–126. 

- [29] S. Ostadabbas, M. Baran Pouyan, M. Nourani, and N. Kehtarnavaz, “In-bed posture classification and limb identification,” in Proc. IEEE Biomed. Circuits Syst. Conf. Proc., 2014, pp. 133–136. 

- [30] J. J. Liu, M.-C. Huang, W. Xu, and M. Sarrafzadeh, “Bodypart localization for pressure ulcer prevention,” Proc. 36th Annu. Int. Conf. IEEE Eng. Med. Biol. Soc., 2014, pp. 766–769. 

- [31] H. M. Clever, A. Kapusta, D. Park, Z. Erickson, Y. Chitalia, and C. C. Kemp, “3D human pose estimation on a configurable bed from a pressure image,” in Proc. IEEE/RSJ Int. Conf. Intell. Robots Syst., 2018, pp. 54–61. 

- [32] H. M. Clever, Z. Erickson, A. Kapusta, G. Turk, C. K. Liu, and C. C. Kemp, “Bodies at rest: 3D human pose and shape estimation from a pressure image using synthetic data,” in Proc. IEEE/ CVF Conf. Comput. Vis. Pattern Recognit., 2020, pp. 6214–6223. 

- [33] M. Andriluka, L. Pishchulin, P. Gehler, and B. Schiele, “2D human pose estimation: New benchmark and state of the art analysis,” in Proc. IEEE Conf. Comput. Vis. Pattern Recognit., 2014, pp. 3686–3693. 

- [34] S. Johnson and M. Everingham, “Clustered pose and nonlinear appearance models for human pose estimation,” in Proc. Brit. Mach. Vis. Conf., 2010, pp. 1–11. 

- [35] B. Sapp and B. Taskar, “MODEC: Multimodal decomposable models for human pose estimation,” in Proc. Conf. Comput. Vis. Pattern Recognit., 2013, pp. 3674–3681. 

- [36] T.-Y. Lin et al., “Microsoft COCO: Common objects in context,” in Proc. Eur. Conf. Comput. Vis., 2014, pp. 740–755. 

- [37] M. Martinez, L. Rybok, and R. Stiefelhagen, “Action recognition in bed using BAMs for assisted living and elderly care,” in Proc. 14th IAPR Int. Conf. Mach. Vis. Appl., 2015, pp. 329–332. 

- [38] M.-C. Yu, H. Wu, J.-L. Liou, M.-S. Lee, and Y.-P. Hung, “Multiparameter sleep monitoring using a depth camera,” in Proc. Int. Joint Conf. Biomed. Eng. Syst. Technol., 2012, pp. 311–325. 

- [39] S. Johnson and M. Everingham, “Learning effective human pose estimation from inaccurate annotation,” in Proc. IEEE Conf. Comput. Vis. Pattern Recognit., 2011, pp. 1465–1472. 

- [40] X. Liang, K. Gong, X. Shen, and L. Lin, “Look into person: Joint body parsing & pose estimation network and a new benchmark,” IEEE Trans. Pattern Anal. Mach. Intell., vol. 41, no. 4, pp. 871–885, Apr. 2018. 

- [41] S. Liu and S. Ostadabbas, “Inner space preserving generative pose machine,” in Proc. Eur. Conf. Comput. Vis., 2018, pp. 718–735. 

- [42] T. Xiang, G.-S. Xia, and L. Zhang, “Image stitching with perspective-preserving warping,” 2016, arXiv:1605.05019. 

- [43] R. Hartley and A. Zisserman, Multi. View Geometry in Comput. Vis. Cambridge, U.K.: Cambridge Univ. Press, 2003. 

- [44] B. Xiao, H. Wu, and Y. Wei, “Simple baselines for human pose estimation and tracking,” in Proc. Eur. Conf. Comput. Vis., 2018, pp. 472–487. 

- [45] G. Gkioxari, A. Toshev, and N. Jaitly, “Chained predictions using convolutional neural networks,” in Proc. Eur. Conf. Comput. Vis., 2016, pp. 728–743. 

- [46] W. Yang, S. Li, W. Ouyang, H. Li, and X. Wang, “Learning feature pyramids for human pose estimation,” in Proc. IEEE Int. Conf. Comput. Vis., 2017, pp. 1281–1290. 

- [47] X. Chu, W. Yang, W. Ouyang, C. Ma, A. L. Yuille, and X. Wang, “Multi-context attention for human pose estimation,” in Proc. IEEE Conf. Comput. Vis. Pattern Recognit., 2017, pp. 1831–1840. 

- [48] D. P. Kingma and J. Ba, “Adam: A method for stochastic optimization,” 2014, arXiv:1412.6980. 

- [49] Z. Zhong, L. Zheng, G. Kang, S. Li, and Y. Yang, “Random erasing data augmentation,” 2017, arXiv:1708.04896. 

- [50] E. S. Shahin, T. Dassen, and R. J. Halfens, “Pressure ulcer prevalence in intensive care patients: A cross-sectional study,” J. Eval. Clin. Pract., vol. 14, no. 4, pp. 563–568, 2008. 

- [51] J. Black et al., “National pressure ulcer advisory panel’s updated pressure ulcer staging system,” Adv. Skin Wound Care, vol. 20, no. 5, pp. 269–274, 2007. 

- [52] M. R. Ronchi, O. Mac Aodha, R. Eng, and P. Perona, “It’s all relative: Monocular 3D human pose estimation from weakly supervised data,” in Brit. Mach. Vis. Conf., p. 300, Sep. 2018. [Online]. Available: https://dblp.org/rec/bib/conf/bmvc/RonchiAEP18 

- [53] X. Zhou, Q. Huang, X. Sun, X. Xue, and Y. Wei, “Towards 3D human pose estimation in the wild: A weakly-supervised approach,” in Proc. IEEE Int. Conf. Comput. Vis., 2017, pp. 398–407. 

- [54] G. Moon, J. Y. Chang, and K. M. Lee, “Camera distance-aware top-down approach for 3D multi-person pose estimation from a single RGB image,” in Proc. IEEE Conf. Int. Conf. Comput. Vis., 2019, pp. 10132–10141. 

- [55] F. Xiong et al., “A2J: Anchor-to-joint regression network for 3D articulated pose estimation from a single depth image,” in Proc. IEEE Int. Conf. Comput. Vis., 2019, pp. 793–802. 

- [56] A. Haque, B. Peng, Z. Luo, A. Alahi, S. Yeung, and L. Fei-Fei , “Towards viewpoint invariant 3D human pose estimation,” in Proc. Eur. Conf. Comput. Vis., 2016, pp. 160–177. 

- [57] R. I. Hartley and A. Zisserman, Multiple View Geometry in Computer Vision, 2nd ed. Cambridge, U.K.: Cambridge Univ. Press, 2004. 

- [58] R. Szeliski, Computer Vision: Algorithms and Applications. Berlin, 

Germany: Springer, 2010. 

Shuangjun Liu received the BSc and MSc degrees in mechatronics from the Dalian University of Technology, Dalian, China, in 2009 and 2012, respectively. In 2017, he is currently working toward the PhD degree with Augmented Cognition Lab, Electrical and Computer Engineering Department, Northeastern University. His research intrests include visual perception problems under adverse vision conditions or limited data with the working example of human pose estimation. 

Xiaofei Huang received the BSc degree in electronic engineering, the MSc degree in mechanical manufacture and automation from the Wuhan University of Technology, China, 2010, and 2013 respectively, and the MSc degree in computer engineering from the Northeastern University, Boston, Massachusetts in 2017. She is currently working toward the PhD degree with the Electrical and Computer Engineering Department, Northeastern University, Boston, Massachusetts. Her research intrests include infant behavior learning with limited data. 

Authorized licensed use limited to: Nazarbayev University. Downloaded on June 30,2026 at 07:52:32 UTC from IEEE Xplore.  Restrictions apply. 

IEEE TRANSACTIONS ON PATTERN ANALYSIS AND MACHINE INTELLIGENCE, VOL. 45, NO. 1, JANUARY 2023 

1118 

Nihang Fu received the BSc degree in electrical engineering and automation from the Chongqing Jiaotong University, Chongqing, China in 2019 and the MSc degree in electrical and computer engineering from the Northeastern University, Boston, Massachusetts in 2021. She is currently working toward the PhD degree with the Computer Science and Engineering Department, University of South Carolina, Columbia, South Carolina. Her research interests include data efficient infant pose and posture recognition. 

Cheng Li received the BSc degree in electrical engineering from the Huazhong University of Science and Technology, Wuhan, China in 2010 and the MSc degree in computer engineering from the Northeastern University, Boston, Massachusetts in 2019. He is currently a data scientist with the AstrumU Inc., Kirkland, Washington, where he applies his knowledge in natural language processing, image processing and image recognition methods for the construction of AI translation engine. 

Zhongnan Su received the BSc degree in telecommunication engineering from the Jilin University, Changchun, China in 2017 and the MSc degree in computer engineering from the Northeastern University, Boston, Massachusetts in 2020. He is currently working with the Amazon Web Service focusing on the development of query engine and database, and business intelligence tools. 

Sarah Ostadabbas received the BSc degree in both electrical and biomedical engineering from the Amirkabir University of Technology, Tehran, Iran, in 2005 and the MSc degree in control engineering from the Sharif University of Technology, Tehran, Iran, in 2007, and the PhD degree in electrical engineering from the University of Texas at Dallas in 2014. She is currently an assistant professor with the Electrical and Computer Engineering Department, Northeastern University, Boston, Massachusetts, where she directs the Augmented Cognition Lab (ACLab). Her research intrests include the intersection of computer vision and machine learning with a multidisciplinary application in understanding, estimating, and predicting human behaviors. 

> " For more information on this or any other computing topic, please visit our Digital Library at www.computer.org/csdl. 

Authorized licensed use limited to: Nazarbayev University. Downloaded on June 30,2026 at 07:52:32 UTC from IEEE Xplore.  Restrictions apply. 

