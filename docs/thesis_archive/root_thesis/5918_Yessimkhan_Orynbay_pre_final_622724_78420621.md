### **Designing of Omni Directional, Autonomous and AI** **Controlled Ball Launcher**

#### **Yessimkhan Orynbay** **201713885** **Submitted to the Department of Electrical and Computer** **Engineering** **in fulfillment of the requirements for the degree of** **Master of Electrical and Computer Engineering** **School of Engineering and Digital Science** **Department of Electrical and Computer Engineering** **Nazarbayev University** 53 Kabanbay batyr avenue Astana, Kazakhstan, 010000 Supervisor: Sultangali Arzukylov Co-supervisor: Mohammad Hashmi Nazarbayev University June 2025 © Yessimkhan Orynbay, 2025. The author hereby grants to NU permission to reproduce and to distribute publicly paper and electronic copies of this thesis document in whole or in part in any medium now known or hereafter created.


## **DECLARATION**

I hereby, declare that this manuscript, entitled “Designing of Omni


Directional, Autonomous and AI Controlled Ball Launcher”, is the result of


my own work except for quotations and citations which have been duly


acknowledged. I also declare that, to the best of my knowledge and belief, it


has not been previously or concurrently submitted, in whole or in part, for


any other degree or diploma at Nazarbayev University or any other national


or international institution.


Signature(s):


Name: **Yessimkhan** **Orynbay**


Date: 2026


#### **Abstract**

This work began as a way to improve football training by providing steady, accurate
passes without needing an extra person. The project designs an omnidirectional,
AI-based ball launcher that combines mechanical hardware, aerodynamic flight modeling, and real-time computer vision. A lightweight aluminum chassis and carefully
selected motors keep the system mobile while maintaining safe operation. Drag, lift,
and spin forces are included in the ball-flight model to support precise launches.
Reinforcement learning methods such as Proximal Policy Optimization (PPO) and
Deep Deterministic Policy Gradient (DDPG) are then used to adapt the aim based
on observed outcomes. Early tests indicate that the launcher gradually improves its
accuracy, delivering the ball closer to the intended target. By automating repetitive
passing tasks, players can focus on skill development while training becomes more
efficient and consistent.


3


### **Acknowledgments**

I would like to thank my supervisor, Sultangali Arzykulov, for his guidance and


support and for giving us all the help possible during this project. I would like to


express my gratitude for all the equipment, test beds and materials that he provided


to us, which were fundamental to this project.


I would also like to express my appreciation to Nazarbayev University for the


environment and facilities they have provided to us.


I would also like to express my gratitude to my co-supervisor Mohammad Hashmi


for his guidance, support and sharing his knowledge with us during this research.


4


# **Contents**

**Abbreviation** **List** **7**


**1** **Introduction** **9**


1.1 Problem Statement . . . . . . . . . . . . . . . . . . . . . . . . . . . . 11


**2** **Literature** **Review** **13**


2.1 Hardware . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 13


2.1.1 Frame and wheels . . . . . . . . . . . . . . . . . . . . . . . . . 13


2.1.2 Motor selection and power calculation . . . . . . . . . . . . . 13


2.1.3 Omni-directional chassis design . . . . . . . . . . . . . . . . . 14


2.2 Ball aerodynamics and flight dynamics . . . . . . . . . . . . . . . . . 14


2.2.1 Ball flight equations . . . . . . . . . . . . . . . . . . . . . . . 14


2.2.2 Ball flight simulations . . . . . . . . . . . . . . . . . . . . . . 18


2.3 Control and AI implementation . . . . . . . . . . . . . . . . . . . . . 20


2.4 Visual recognition of ball and target . . . . . . . . . . . . . . . . . . . 21


2.4.1 Visual processing hardware for detection and tracking . . . . . 21


2.4.2 AI-assisted aiming adjustments . . . . . . . . . . . . . . . . . 22


2.4.3 Weilding machine learning for better aim . . . . . . . . . . . . 24


**3** **Methodology** **26**


3.1 Mechanical design methodology . . . . . . . . . . . . . . . . . . . . . 27


3.1.1 Chassis and structural framework . . . . . . . . . . . . . . . . 27


3.1.2 Wheel and motor configuration . . . . . . . . . . . . . . . . . 27


5


3.1.3 Platform for omni-directional movement . . . . . . . . . . . . 30


3.2 Ball aerodynamics and flight dynamics . . . . . . . . . . . . . . . . . 32


3.2.1 Trajectory modeling . . . . . . . . . . . . . . . . . . . . . . . 32


3.2.2 Simulation tools . . . . . . . . . . . . . . . . . . . . . . . . . . 34


3.3 Control system and electronics . . . . . . . . . . . . . . . . . . . . . . 37


3.3.1 Hardware control setup . . . . . . . . . . . . . . . . . . . . . . 37


**4** **System** **Testing** **and** **Training** **43**


4.1 Experimental Environment and 3D Projection . . . . . . . . . . . . . 43


4.2 Ball and Pose Detection Systems . . . . . . . . . . . . . . . . . . . . 45


4.3 User Interface and Voice Control Integration . . . . . . . . . . . . . . 46


4.4 Low-Level Hardware Control and Integration . . . . . . . . . . . . . . 46


4.5 AI Aiming and Reinforcement Learning Training . . . . . . . . . . . . 47


4.5.1 AI Aiming and Reinforcement Learning Training . . . . . . . 47


**5** **Results** **and** **Discussions** **50**


5.1 Results and Discussions . . . . . . . . . . . . . . . . . . . . . . . . . 50


5.1.1 Subsystem Performance Evaluation . . . . . . . . . . . . . . . 50


5.1.2 Responsiveness of the mechanical and overall system . . . . . 51


**A** **Figures** **54**


6


# **Abbreviation List**

**AC** Alternating Current


**AI** Artificial Intelligence


**BLDC** Brushless DC


**BLE** Bluetooth Low Energy


**CFD** Computational Fluid Dynamics


**CV** Computer Vision


**DC** Direct Current


**DDPG** Deep Deterministic Policy Gradient


**DOF** Degree of Freedom


**E-STOP** Emergency Stop


**ESC** Electronic Speed Controller


**ESP32** Espressif 32-bit Microcontroller


**GPU** Graphics Processing Unit


**GT** Ground Truth


**IMU** Inertial Measurement Unit


**LLM** Large Language Model


7


**mAP** Mean Average Precision


**ODE** Ordinary Differential Equation


**PMDC** Permanent Magnet DC


**PPO** Proximal Policy Optimization


**PWM** Pulse Width Modulation


**ReLU** Rectified Linear Unit


**RGB** Red, Green, Blue


**RL** Reinforcement Learning


**RPM** Revolutions Per Minute


**SST** Speech-to-Text


**USB** Universal Serial Bus


**YOLO** You Only Look Once


8


# **Chapter 1** **Introduction**

Football players constantly practise and improve their reaction, receiving and passing


skills. Two challenges that arise when training are (i) continuously supplying the ball


to the player and (ii) providing accurate and consistent passes. A ball-launcher can


help football players practice their weak points by regularly providing situations of


interest.


The typical ball-launcher mechanism includes two wheels that are horizontally


mounted and counter-rotating. The ball is fed between the wheels and is accelerated


by friction. If the two wheels are at a different speed, the ball will be given backspin,


leading to a curved trajectory because of aerodynamic effects: details are provided


in studies that analyse ball trajectories [5]. Accurately launched balls can be used to


teach specific skills.


But aiming manually will make it hard to repeat a given trajectory. One limita

tion on many existing prototypes is that aiming and adjusting the trajectory are all


manual, and even when operated carefully, not all desired target points can be reached


accurately in the first trial. So, the objective of this thesis is to create an omnidi

rectional ball-launcher that automatically aims and shoots with a desired trajectory


from various locations on the field.


For realistic trajectories, we must take into account aerodynamic effects such as


drag and lift [4]. It is also important that the launcher can move omnidirectionally


in three dimensions [6]. In the mechanical design phase, the device’s range also needs


9


to be considered. For instance, depending on wheel size, the wheel can spin at speeds


between 500 rpm and 4500 rpm. Faster wheel speed leads to more stringent safety


considerations and vibration problems, such as bolt loosening.


The second key element is a three-dimensional trajectory simulator for the ball


with initial conditions such as speed, rotational speed, mass, diameter, etc., and aero

dynamic variables [1]. Appropriate initial conditions are estimated from simulation


and then fed to the launcher control to specify the wheel rotational speeds and the


launcher position (tilt, angle, aim).


Aiming will not self-improve. As such, a self-improving approach from machine


learning is adopted [2]. Camera-based computer vision can provide information re

garding trajectory and ball position, as do systems that estimate ball spin rate, veloc

ity and launch position [3]. The system involving simulation, actuation and feedback


from cameras constitutes a closed-loop system and can be studied and improved using


AI.


Figure 1-1: Preliminary prototype of the ball launcher.


10


### **1.1 Problem Statement**

Data-driven training methods are becoming more prevalent to enhance football skills


like passing accuracy, reaction speed, and ball control. But current practice still relies


heavily on human intervention (e.g., coach or team mate) during training, which can


lead to inconsistency, fatigue and variability in ball delivery. As previously mentioned,


precise and repeatable passes in the training environment are a challenge.


Novel training solutions such as the Footbonaut system have shown that high

speed and repeatable ball delivery contributes to better ball control and rapid decision

making in professional soccer players. Likewise, automated training systems like


FOOTBOT underscore the benefits of consistent training scenarios. Research in


motor learning also supports this notion that repeated and consistent stimuli are


necessary for skill learning and performance [19,20].


However, current systems are not without their shortcomings. They are costly,


immobile and confined to high-end facilities. They often lack intuitive intelligence


and feedback, relying on pre-planned motion trajectories. In terms of control, with

out feedback implementation, precision and flexibility are limited when operating in


dynamic environments [21].


The latest developments in machine learning, especially reinforcement learning, of

fer a potential solution. These include Deep Deterministic Problem Gradient (DDPG)


and Proximal Policy Optimization (PPO) algorithms, which have been successful in


continuous control and robotics [22,23]. These methods allow a system to learn and


adapt to feedback in order to enhance performance.


Another major challenge is the absence of quantitative and consistent training


environments for performance measurement. To evaluate player performance, it is


important to provide consistent inputs, which can be challenging for human opera

tors. Sports analytics literature reports that a controlled environment is crucial for


performance evaluation and analysis of tactical strategies [24].


Consequently, we need an intelligent, autonomous and adaptive ball launcher that


can provide repeatable and accurate passes with real-time feedback and learning con

11


trol. This approach would improve the training process and allow for performance


measurement of players based on data, and is therefore highly relevant for football


training.


12


# **Chapter 2** **Literature Review**

### **2.1 Hardware**

#### **2.1.1 Frame and wheels**

Earlier studies [6] show that the main chassis is required to accommodate components


and withstand the stresses during high-speed ball release, yet be lightweight enough to


allow for movement and autonomy. Such chassis are commonly made from aluminum


alloys. Aluminum 6061 is commonly used for its good specific strength [7].


A few studies mention enhancing wheel-to-ball contact with polyurethane wheel


covers [6,8,9]. Polyurethane coverings can help provide higher co-efficient of friction,


wear resistance, and improved grip qualities, which is desirable for uniform accelera

tion of the ball.

#### **2.1.2 Motor selection and power calculation**


Motor choice is a key design consideration as it can impact the wheel speed, torque,


cost, noise, and motor size. A study [10] suggests trade-offs between permanent

magnet DC (PMDC) motors and brushless DC (BLDC) motors. PMDC motors are


generally more affordable and PMDC motors tend to be quieter and smaller but


costlier.


This study [10] describes using a PMDC motor (MY1016, 350 W, 2700 rpm)


13


for initial prototyping because of cost concerns with ball velocities around 36 m/s


for a 22 cm diameter soccer ball. It was calculated that about 200 W of power is


sufficient to achieve the desired ball speed, so this decision was justified. It is also


common to use existing wheels (e.g., go-kart wheels) to save time and money during


prototyping [11].

#### **2.1.3 Omni-directional chassis design**


For omnidirectional firing, earlier work [6] mentions using either gimbal platforms


(usually 3 DOF: roll, pitch and yaw) or Stewart platforms (6 DOF). Gimbals are


commonly used to reduce vibration in applications that seek to stabilise, while Stewart


platforms can provide very precise positioning with large loads. A combination of both


may also be used, for instance Stewart actuation for pitch and gimbal motors for roll


and yaw [6].


(a) Gimbal platform. (b) Stewart platform.


Figure 2-1: Gimbal and Stewart platforms [6].

### **2.2 Ball aerodynamics and flight dynamics**

#### **2.2.1 Ball flight equations**


Aerodynamics of ball flight are critical to flight planning. Reynolds number is an


important dimensionless quantity for soccer ball flight, and takes values in the range


14


70,000-500,000 [5]. Here a variety of transitional boundary-layer behaviours may


occur. This affects the shape of the velocity profile near the wall, leading to a shift


in the point of separation and potentially a dramatic change in the drag (referred


to as a “drag crisis”) and unstable, unpredictable ball-flight behaviour (the so-called


knuckleball) [25,26].


The nature of the boundary-layer velocity profiles for laminar and turbulent


boundary layers is shown qualitatively in Figure 2-2. The turbulent profile is fuller


due to increased mixing of the near-wall flow and is associated with delayed flow


separation and lower pressure drag force than a laminar boundary layer [26].


Figure 2-2: Illustrative laminar vs. turbulent boundary-layer velocity profiles and
their connection to separation behaviour and aerodynamic drag on a ball [26].


The ball is slowed by aerodynamic drag, in addition to gravity. To model soccer

ball motion, gravity can no longer be considered the only force acting on the ball,


and must be complemented with aerodynamic drag and lift forces due to ball spin.


Previous work on modelling free kicks and soccer-ball flight reveals that the ball does


not behave like a projectile; aerodynamic forces have significant effects on both ball


15


range and lateral displacement [27–29]. Specifically, the curved trajectory seen in


many soccer shots is largely due to the Magnus effect, and non-smooth unpredictable


motion seen in shots with low-spin and high speed is related to variations in flow


separation and drag coefficient [25,29].


Newton’s second law can be used to write the translational ball motion as


_𝑚_ _[𝑑]_ **[v]** (2.1)

_𝑑𝑡_ [=] _[ 𝑚]_ **[g]** [ +] **[ F]** _[𝐷]_ [+] **[ F]** _[𝐿][,]_


where _𝑚_ is the ball mass, **v** is the velocity vector, **g** is gravitational acceleration, **F** _𝐷_


is the drag force, and **F** _𝐿_ is the lift force.


This decomposition of the external forces is helpful because the different terms


have distinct physical interpretations: gravity produces an overall downwards accel

eration, drag is in the opposite direction to the instantaneous ball velocity and acts


to shorten the range, and lift is due to the ball spin and can deflect the trajectory to


the left or right (and/or up or down, Magnus effect) [29].


Figure 2-3 shows this force balance for any spinning ball in flight and is used to


motivate the aerodynamic terms in the model.


Figure 2-3: Forces acting on a spinning soccer ball in flight (gravity, aerodynamic
drag, and Magnus lift) [29].


16


The drag force is commonly expressed as


**F** _𝐷_ = _−_ [1] (2.2)

2 _[𝜌𝐶][𝐷][𝐴][‖]_ **[v]** _[‖]_ **[v]** _[,]_


where _𝜌_ is air density, _𝐶𝐷_ is the drag coefficient, and _𝐴_ = _𝜋𝐷_ [2] _/_ 4 is the frontal area


of a ball of diameter _𝐷_ [27,29]. The lift force caused by ball spin may be written as


**F** _𝐿_ = [1] (2.3)

2 _[𝜌𝐶][𝐿][𝐴][‖]_ **[v]** _[‖]_ [2] **[^n]** _[,]_


where _𝐶𝐿_ is the lift coefficient and **^n** is a unit vector normal to the plane defined by


the spin vector and velocity vector [28,30].


There are two nondimensional numbers of particular note in soccer-ball aerody

namics. The first is the Reynolds number,


_𝑅𝑒_ = _[𝜌𝑉𝐷]_ _,_ (2.4)

_𝜇_


describes the flow around the ball, where _𝑉_ is ball speed and _𝜇_ is dynamic viscosity


of air. and the second is the spin parameter,


_𝑆_ = _[𝜔𝑅]_ (2.5)

_𝑉_ _[,]_


where _𝜔_ is the angular velocity of the ball and _𝑅_ is the ball radius [25,31]. The


values of _𝐶𝐷_ and _𝐶𝐿_ are greatly affected by these parameters. It has been experimen

tally demonstrated that the drag coefficient is speed-dependent for the full range of


motion of a soccer ball; it varies according to the Reynolds number and may undergo


a drag crisis around the critical Reynolds number, which in turn strongly influences


the range and stability of a ball’s flight [25,30,32].


For these reasons, the aerodynamic terms of a realistic launcher model should not


be constant across all conditions. It is more accurate to express the aerodynamic


terms as non-constant speed- and spin-dependent functions, i.e.,


_𝐶𝐷_ = _𝐶𝐷_ ( _𝑅𝑒_ ) _,_ _𝐶𝐿_ = _𝐶𝐿_ ( _𝑅𝑒, 𝑆_ ) _,_ (2.6)


17


so as to be able to better simulate curved passes, dipping shots and variations arising


from wind conditions [30,31].


In practice, these coefficient functions are often obtained (or refined) by compar

ing the simulated trajectory against measured ball-flight data. Trajectory-analysis


techniques assess aerodynamic behaviour using measured trajectories by performing


position-vs-time differentiation to extract velocity and acceleration data and then


adjusting the aerodynamic drag and lift functions until the equations of motion (nu

merically integrated) match the measured trajectory [29]. This process is illustrated


in Figure 2-4, and shows the validation loop between the model (numerical integra

tion) and experiment (ball flights).


Figure 2-4: Trajectory extraction and model-verification workflow used to compare
measured soccer-ball flight with theoretical predictions [29].


These equations and the verification method provide the theoretical grounds for


choosing the launcher wheel speed, pitch angle and spin rate in order to obtain a


prescribed trajectory.

#### **2.2.2 Ball flight simulations**


Trajectory control typically begins with simulation models that involve drag, Magnus


forces, spin decay and Reynolds-number effects on aerodynamic coefficients [5]. Nu

merical integration algorithms are often implemented in MATLAB or Python, and


computational fluid dynamics (CFD) has been used to investigate airflow and verify


models [14]. Simulations of free kicks have included other factors, such as bounce [13].


The governing equations of ball flight are nonlinear and the aerodynamic coefficients


18


depend on velocity and spin, so analytical solutions are unlikely to lead to accurate


predictions of football flight. Therefore, most research uses numerical simulation to


predict the threedimensional ball trajectory for given initial conditions [27, 29, 33].


Numerical simulation allows us to consider the impact of drag, lift, gravity and, if


appropriate, spin decay and other less-analytical effects.


In the literature, simulation models are often used to predict direct free kicks,


curved kicks, and sensitivity of the trajectory to initial launch conditions (initial


speed, elevation angle, azimuth angle, spin rate) These models are generally created


using ordinary differential equation solvers in programs such as MATLAB or Python,


with the state variable composed of ball position and velocity and the aerodynamic


coefficients updated at each iteration based on the flow conditions at that moment [30,


33]. This is particularly relevant in the design of ball launching devices because it


enables the designer to reverse-engineer a landing point or interception point into a


set of launch parameters.


Another important direction in the literature is the use of experimentally derived


aerodynamic data inside simulation models. Drag and lift coefficient curves obtained


from wind-tunnel experiments and trajectory-based studies have been incorporated


into the simulations, resulting in a more realistic representation of the ball’s trajec

tory [30–32]. For instance, using trajectory studies is of particular importance be

cause it estimates aerodynamic behaviour from actual ball trajectories, rather than


static aerodynamic force modelling [30]. This is extremely useful in football, where


familiarisation with a player’s trajectory is more important than a pure theoretical


assessment of the force.


Along with lower-order dynamic simulations, computational fluid dynamics (CFD)


have been used to study the effect of seam shape and ball surface structure on the


air separation and pressure fields of the ball [25,26]. While CFD is more expensive


than generalised ball trajectories, it can inform more about the reason for different


drag and lift force behaviour on different balls. So, CFD can be applied as an adjunct


tool, while simpler numerical models of ball flight are more applicable for real-time


control and implementation.


19


The ball-flight simulation is important for the proposed launcher for two reasons.


First, it offers a physics-based approach to predicting the rotational speed of wheels,


the launch direction and spin needed to hit a target. Second, it creates a model


that can be used in combination with feedback from the camera and reinforcement


learning to improve targeting accuracy with each launch. So simulation serves not


only a design purpose, but also as a basis for closed-loop intelligent control of the


launcher system.

### **2.3 Control and AI implementation**


Subsection: Hardware control unit and logical processing Small computer vision and


learning algorithms often run on embedded GPU solutions such as NVIDIA Jetson


boards. An omnidirectional soccer robot with aiming and shooting using cameras


has been demonstrated using Jetson Nano [15]. Other applications include observing


and predicting ball trajectories [16] and robotic ball collection using deep learning


acceleration [17].


A ball-launcer system needs a hierarchical control structure with decoupled high

level perception, decision-making and low-level actuation. In embedded robotic soc

cer, this is typically achieved by using an embedded computer for image processing,


object recognition, state estimation and task control logic, while low-level motor con

trol and time-critical commands are handled by dedicated controllers [34–36]. This


approach is particularly important for the proposed launcher as the system needs to


be able to simultaneously process images, determine the target’s position, calculate


the launch parameters and control several actuators with minimal latency.


The robot-soccer literature demonstrates that real-time vision and decision-making


can be embedded in a system to enable on-board control with size and power con

straints [34,35,37]. In these platforms, the embedded PC is used to execute logical


processing operations such as object detection, map transformation, trajectory es

timation and command computation. These data are then passed on to low-level


controllers for wheel or motor control. This approach can also be applied to a ball


20


launcher: the high-level computer defines the direction and elevation to shoot the ball


and the wheel speed, while the low-level controller accurately and safely reaches the


desired set points.


In systems with high-speed motors and dynamic motion, low-level control is of


particular importance. Research with omnidirectional robots reports that closed

loop control systems respond faster and are more robust when the robot is subject


to changes and disturbances [36]. Furthermore, telemetry-based tuning techniques


have been proposed to improve the capability of PI-controllers for omnidirectional


robots by demonstrating that reliable low-level control can improve the quality of


the movement [36]. Similar concepts are readily extendable to the proposed launcher


to regulate motor speed, minimize transient error, and repeatable ball launching


conditions.


This means that the proposed system should contain a hardware control unit


with an embedded computing device for perception and high-level processing, as well


as hardware for controlling motors in a closed-loop manner. The separation of tasks


enhances modularity and enables real-time processing of the visual information, while


providing the basis for future integration of more sophisticated control strategies and


learning algorithms [34,35].

### **2.4 Visual recognition of ball and target**

#### **2.4.1 Visual processing hardware for detection and tracking**


Video cameras and multiple cameras are frequently used for ball position and spin


estimates. Two cameras have been used to estimate 3D position and spin parameters


[18]. Fast frame rates also enable accurate estimation of aerodynamic data [5].


Target tracking is critical to allow the launcher to see the ball and target (intended


player or goal) and the consequences of each shot. Omnidirectional and monocular


cameras have been extensively used in robotic-soccer research for real-time detection


of balls, goals, field boundaries and other robots [35, 38, 39]. Omnidirectional cam

21


eras offer a broad field of view for awareness and monocular forward-facing cameras


offer greater resolution for target detection. The choice is based on the application,


particularly the balance of coverage, accuracy and processing efficiency.


Conventional robotic-soccer vision systems typically used color segmentation and


shape information for efficient detection of relevant objects [38,39]. These approaches


are fast and can work well in environments where lighting and background conditions


are constrained. But they are prone to sensitivity to lighting conditions, background


noise and ball shape. Recent research has improved the robustness of object detection


by using deep-learning-based detectors, which learn visual features from data [35,37,


40]. This is particularly significant in modern training settings where illumination


changes, player appearance, and background clutter can be significant.


The other important factor is embedded implementation. Recent studies have


demonstrated that lightweight deep detectors (such as SSD-MobileNet) and small


neural networks for object detection can operate in real-time on resource-restricted


robot soccer platforms [35,37,40]. This suggests that it is possible to achieve practical


detection without offloading to hard computers. For the launcher, this implies that


the camera system can be seamlessly integrated with the embedded control system


to detect and track the ball and the goal in real-time.


Using additional temporal information with frame-based detection can improve


tracking. In robot-soccer, ball and target tracking is required to provide information


about relative angle, distance and relative motion, which is essential for responsive


control [39,41]. As such, the proposed launcher should include a camera system and


ball/player detection hardware with a frame rate, field of view, and computational


power that enable continuous detection of the ball and target.

#### **2.4.2 AI-assisted aiming adjustments**


In AI-assisted aiming, ball/goal detection can be done using OpenCV and a multi

DOF launcher can provide the necessary degrees of freedom to produce different


trajectories [6].


The aiming of an autonomous launcher cannot rely fully on a static calibration


22


because operations in practice involve uncertainties such as delays, slips, ball defor

mations, and noise. A better approach is to use camera feedback so that the launcher


can provide feedback on the difference between target location and launch outcome.


This concept is similar to that of visual servoing, in which vision is used within the


control loop to drive iterative reduction of positioning errors [42]. In the proposed


launcher, visual features such as target position, ball position and landing error can


be used to correct the launcher’s orientation and wheel control after each shot.


There are some examples from robot soccer. Visual sensors have been employed to


determine the relative pose of the ball and goal to help robots align before shooting


goals and/or passing the ball [39, 41]. In these cases, the control decision is made


based on the geometric error of the current observation and the desired visual setup.


The same concept can be applied to the ball launcher: after identifying the target


player or target aiming point, the controller can calculate angular error in the image


plane and translate it to yaw and pitch adjustments for the launcher.


Artificial intelligence can be especially useful when the target is moving or repeated


kicking reveals systematic bias. Rather than relying simply on the pre-calibrated


table, the system can combine dynamics-based trajectory prediction for the ball with


the observed error and update the aiming direction. This combined approach is less


sensitive to the model and can accommodate operating conditions. Recent work in


humanoid soccer also demonstrates that vision-based goal alignment and ball tracking


can be improved with state-of-the-art object dectors run on an embedded device [41].


This suggests that AI-assisted aiming can be a viable means to increase the precision


of shots in autonomous training devices.


So, AI-assisted aiming adjustments to the proposed launcher should be viewed as a


closed loop error correction process where computer vision provides the measurements


and the controller sets the launch parameters to reduce the observed visual error.


This approach can enhance accuracy, eliminate the need for manual calibration and


facilitate a more dynamic training experience.


23


#### **2.4.3 Weilding machine learning for better aim**

Machine learning can increase the achieved accuracy over multiple shots through


miss distance feedback. Some research in this area explores the use of reinforcement


learning such as the Proximal Policy Optimization (PPO) algorithm for stable tuning


and Deep Deterministic Policy Gradient (DDPG) for continuous control optimization


[12].


While physics models are necessary to calculate initial launch parameters, they are


unable to eliminate error in practice. The real world mapping between launching mo

tor actions and ball landing position is influenced by nonlinear and partially unknown


system dynamics, including variation in friction, motor dynamics, and aerodynamic


forces. Machine learning can address such remaining errors, learning corrective map

pings from repeated interactions with the system while launching [10, 11]. For the


launcher proposed here, this could be a model that takes the miss distance, target


location, and initial actuation as inputs, and informs aiming in subsequent launches.


Reinforcement learning is well-suited to this task in particular because the continu

ous action variables for the launcher, which include wheel speed, differential speed and


aiming angle, have to be learned. The Deep Deterministic Policy Gradient (DDPG)


method was developed to learn policies for continuous control and is now a common


approach for learning policies for high-dimensional actuator systems [22]. Proximal


Policy Optimization (PPO) is also a popular method which stabilises training with


a clipped objective function and has demonstrated excellent empirical performance


in a variety of robotic control tasks [23,43]. These approaches are applicable to the


launcher given that aiming requires continuous adjustments to the parameters.


Recent research in robotics and robot-soccer indicates that deep reinforcement


learning can be applied to embodied control systems. For instance, reinforcement


learning has been applied to generate policies for humanoid robot soccer players,


where policies can be learned from interaction and refined through an iterative pro

cess [44]. Policy-gradient methods have also been applied to humanoids, confirming


the suitability of the PPO decision making system in robotics [45]. And in the


24


robotics field overall, a recent survey suggests deep reinforcement learning is increas

ingly playing a more important role in robotics when integrated with simulation,


expert knowledge and real-world experience [43].


For the new launcher, a learning-based aiming system can be developed to include


the position of the target, the current launcher pose, the wheel speeds and the ob

served miss distance in the state, and the changes to the launch parameters in the


action. We can then design a reward function that penalises miss distance and also


encourages repeatability. Thus the launcher can learn to better aim over time. Hence,


machine learning and, in particular, reinforcement learning, can be used to convert the


launcher from an operator-tuned, fixed tool into a self-regulating, adaptive training


device.


25


# **Chapter 3** **Methodology**

This chapter outlines the stages of research from initial prototyping to preliminary


experimental findings. The flow of the methodology is shown in Figure 3-1.


Figure 3-1: Flowchart of methodology process.


26


### **3.1 Mechanical design methodology**

#### **3.1.1 Chassis and structural framework**

The first phase of mechanical testing was undertaken with a wooden chassis. The


first chassis was made of wood due to its low cost, ease of machining and the ability


to quickly change the chassis structure at the early stage of development. As such,


it was used to conduct rapid testing of primary equipment and sub-systems, such as


motor location, wheel arrangement and primitive launcher design.


But the wooden chassis was only used for preliminary testing. While it was easy


to work with, it was not strong enough to handle high velocities. When tested, the


frame was not very rigid and more prone to vibration caused by lack of stability.


Thus, the wooden chassis was deemed suitable for initial testing of the device, but a


more structurally sound chassis was needed for the rest of the project.


The chassis supports the device, dissipates vibration and should be strong enough


to support the weight of the motor, as well as shocks created due to quick movements


and changes in speed. It also needs to be light to allow mobility. Aluminum alloys


such as AL-6061 are often applied for structural elements [7]. Here, the main frame is


constructed from 30 _×_ 30 mm aluminum construction profile. The desired geometry is


achieved by using corner connections, nuts and bolts. Parts used are shown in Figure


3-2.

#### **3.1.2 Wheel and motor configuration**


Following chassis completion, the wheel and motor system was designed and tested


with a range of motor-wheel combinations. We explored using either brushed DC


motors or three-phase "brushless" DC (BLDC) motors, as we have done with our


previous designs [10]. Brushed DC motors were initially used to ease implementation


for iterative prototyping, simplification of connection, and the ability to control the


motor using readily available DC motor speed controllers. This allowed them to be


used for initial trials of wheel rotation, launcher design and acceleration of the ball.


27


(a) View 1. (b) View 2.


Figure 3-2: Aluminum construction of the launcher frame.


But brushed DC motors also exhibited noise, brush wear, and a less accurate speed


control.


The launcher also considered using a three-phase BLDC motor. They offer more


efficient and smoother rotation and better controllability at high speeds, which was


essential for repeatable launch conditions. The ODrive v3.6 controller was used to


drive BLDC motors in closed loop and allow for accurate speed control. Furthermore,


BLDC drives have regenerative capability during braking, which is indicative of a


more controllable drive system, but again this was not a priority for the launcher.


The power of the motor needs to be high enough to spin the wheels and launch the


ball at the target speed. Earlier studies have shown that 270 W are sufficient for


launching balls rapidly with similar launchers [6]. In this study, 350 W and 2500 W


motors were examined.


Besides the DC and BLDC motors, an AC motor from a washing machine was


also investigated as it was extremely cheap and readily accessible. It was cheap and


easy to get for prototyping and had fast rotational speeds. But it was more difficult


to integrate into the launcher because of power and speed-control issues, and so it


was not as attractive as DC or BLDC motors. A small DC pump motor was also


evaluated for simple prototype testing, but this motor lacked sufficient torque and


power for the primary launching system.


28


Various wheels were also considered for use. Due to the aim for mobility, low-mass


wheels are desirable. Construction wheels were initially available and structurally


strong, but they were also heavy and did not accelerate quickly. Scooter wheels were


smaller and lighter, and thus more efficient for rotational testing. Hoverboard wheels


were also tested due to the ability to readily acquire them and use of a hub-style wheel.


The larger diameter and weight of the hoverboard wheels made them less desirable for


the launcher wheels. Aluminum alloy wheels were selected for the current version due


to their load-bearing capacity and lightweight nature. Later on, a new lighter weight


wheel with a polyurethane coating will be constructed to provide better friction with


the ball [9].


In summary, the choice of motor and wheel were made based on both theoretical


and practical considerations such as availability, control, mechanical fit, and perfor

mance. Through this process, we were able to determine which wheel/motor pairs


worked best to produce consistent ball launches.


Figure 3-3: Three-phase BLDC motor used in the prototype.


For high-speed rotation, it is important to balance the wheels. The initial balance


was done using small weights to counter vibration from an offset center of mass. It


29


was tested at 2500 rpm.


Figure 3-4: Balanced wheel used for preliminary tests.

#### **3.1.3 Platform for omni-directional movement**


To aim the launcher in both the horizontal and vertical directions, an aiming platform


was designed. The objective of this platform was to impart the necessary rotational


motion to the launcher while making it easy to build and modify. Rather than develop


a more sophisticated multi-axis aiming system, a 2-DOF design was chosen as it was


adequate for the aim of the launcher and it could conveniently be integrated into the


launcher frame.


The aiming mechanism was driven by NEMA 23 stepper motors. These motors


were chosen because they are readily available, have high holding torque, and can


be accurately positioned in positioning applications. In this application, the launcher


needed to move within a limited angular range, rather than being able to freely rotate.


Worm gear reducers with a gear ratio of 1:50 were also installed on the motor shafts


to increase the motor output torque and increase stiffness. This enabled the platform


to lift more massive components of the launcher and it also helped to increase the


angular resolution of the overall actuation system.


During the testing, the horizontal reducer exhibited mechanical play with a play


angle of about 2 _[∘]_ . This resulted in a positioning error, particularly when fine aiming


30


Figure 3-5: Mini rollers attached on four sides of the aiming platform to reduce
friction and support smooth sliding motion.


adjustments were made, with the platform not always moving in response to small


movements of the control. The first solution to this problem was to include a feedback


control with a magnetic encoder. This could theoretically eliminate the reducer play,


because the system would know the real angular position and correct the position


of the motor. But, it proved to be inconvenient. The feedback response generated


many unnecessary small adjustments of the mechanism, making it less smooth and


less stable while aiming. It is unclear whether some of this was due to the sensor


itself or to its signal.


So, a series of experiments and calibration tests were performed to study the issue


behind the angular error. Various tuning was done in both hardware and control


program. With multiple rounds of experiments, we found that the backlash issue was


more effectively resolved in the control logic, by adding compensation rather than


relying only on the feedback from the encoder. This improved the stability of the


system and compensated the apparent effect of backlash during aiming.


In addition to the rotary mechanism, small rollers were attached on four sides of


the moving platform.


It was used to provide mechanical support and to reduce friction during sliding.


The mini rollers were meant to reduce friction, to increase mechanical smoothness,


31


and avoid mechanical jamming on non-aimed angular motion of the launcher. This


enhancement improved practical motion of the platform and relieved the mechanical


load on the actuators.


In all, the omnilateral movement platform was designed through repeated exper

imentation with actuator, reducer, sensor and software compensation design. The


resulting design could achieve the desired horizontal and vertical aiming ability while


being mechanically viable for the prototype design. [6].


Figure 3-6: Two-DOF gimbal platform used for aiming.

### **3.2 Ball aerodynamics and flight dynamics**

#### **3.2.1 Trajectory modeling**


In order to predict ball flight, a trajectory model is developed to predict the ball flight


after release from the wheels. This model is used primarily to achieve the desired


ball target from the physical launcher parameters, which are the wheel rotational


speed, wheel speed difference, and launcher orientation relative to the stage. As such,


the trajectory model constitutes the main bridge from the aiming algorithm to the


mechanical launcher.


The ball trajectory is estimated in three dimensions using the main forces that act


32


on the ball in flight. These forces are: gravity, aerodynamic drag and spin-induced


lift (Magnus effect). The drag force slows the ball down and is directed opposite to


the velocity vector, while the Magnus force bends the ball trajectory depending on


the direction and magnitude of the ball spin. As mentioned previously, Reynolds


number also has an influence on the aerodynamic characteristics of the ball as the


aerodynamic coefficients are different for different flow conditions [5]. The initial


conditions for the aerodynamic model are obtained from data reported in trajectory


studies [4].


In practice, initial launch parameters are specified. These are the position of


the ball, the launch speed (in the vertical plane), the launch elevation angle (in the


horizontal plane), and the spin. The launch speed is determined from speeds of


two wheels of the launcher. When both wheels have the same rotational speed, it is


expected that the ball will travel in a straight line, with little curve to the side. When


they are not, the ball spins, which is then accounted for by the model to estimate


curved trajectories. So the wheel speeds are used to generate both speed and spin of


the ball.


Once the initial conditions are specified, the ball trajectory can be calculated in


small increments of time numerically. At each iteration, the drag force and the lift


force are computed from the instantaneous ball velocity and acceleration, velocity,


and position are updated based on these forces. This continues until the ball crosses


the target plane, lands on the ground, or exceeds the acceptable operating range.


This can be done either in MATLAB or Python, using numerical integration solvers


to solve the three-dimensional equations of motion. This approach is more accurate


in predicting ball flight compared to using the 2D projectile equation because it takes


into account deceleration and the influence of spin on the ball trajectory.


The model is not only used to simulate ball flight, but also for launcher control.


Given a target point, the model can be used to predict which settings should be


applied to launch the ball in the direction of the target. This can be achieved in the


early stages by searching for a sufficiently good solution in a trial and error process.


In the second and third stages, this procedure can be accelerated by establishing


33


a mapping between target point and launcher control, thus speeding up the online


estimation process. This can be done via a table, an optimization algorithm, or a


model for corrections.


Because some effects cannot be fully accounted for in the equations, the trajectory


model will also be experimentally calibrated. We can compare the predicted trajectory


with the actual trajectory after a ball has been launched. The discrepancy between


the expected and actual trajectory can be used to tune the aerodynamic coefficients


or perhaps introduce correction factors as software. This will help the model converge


on the true physics of the launcher.


_𝑚_ _[𝑑]_ **[v]** (3.1)

_𝑑𝑡_ [=] _[ 𝑚]_ **[g]** [ +] **[ F]** _[𝐷]_ [+] **[ F]** _[𝐿]_


**F** _𝐷_ = _−_ [1] (3.2)

2 _[𝜌𝐶][𝐷][𝐴][‖]_ **[v]** _[‖]_ **[v]**


**F** _𝐿_ = [1] (3.3)

2 _[𝜌𝐶][𝐿][𝐴][‖]_ **[v]** _[‖]_ [2] **[^n]**


In summary, the trajectory model enables physics-based aiming and control. The


model enables the launcher to predict the flight characteristics of a ball for different


wheel speeds, launch angles and spin, and it provides a foundation for closed-loop


optimisation with visual feedback from the cameras and learning corrections.

#### **3.2.2 Simulation tools**


Numerical solvers in MATLAB or Python are used for trajectory simulations. The


NumPy and SciPy packages in Python include ODE solvers for modelling spin loss


and different weather conditions. In addition to this, CFD simulations (e.g. using


ANSYS Fluent) can be used to gain insight into the airflow around the ball and to


validate these models [14].


In order to investigate the ball after being launched but before implementation


of the full system, a simulation of the ball trajectory was created in MATLAB. The


34


simulation was used to study the effects of various launcher parameters on the ball


trajectory and to estimate whether the desired trajectories can be achieved with the


chosen wheel speeds and aiming angles. The simulation was also intended as an initial


validation prior to implementation of the control algorithm on the real system.


The MATLAB simulation was set up as a 3D numerical simulation of a soccer ball


trajectory over an entire football field. The following standard physical properties


were set for the ball and air: air density, gravitational acceleration, ball mass and


cross-sectional area. Aerodynamic forces such as drag and spin-induced trajectory


were also incorporated. In the present version, the drag influence is applied directly


as a velocity-dependent term, while the spin influence is applied as a Magnus-type


term with exponential decaying angular velocity. This allows the simulation of not


only straight shots, but shots with side spin, topspin and backspin.


Numerical integration of equations of motion was performed using the `ode45` solver


in MATLAB. This solver is suitable for nonlinear dynamic systems and has been


proven adequate for trajectory prediction at this stage of the project. The state


vector contained the position and velocity of the ball in three dimensions. The solver


calculated the ball speed at each time step, accounted for aerodynamic forces and


updated the ball’s translational acceleration. At the same time, the angular velocities


were defined as time-varying components with exponential decay, which allowed to


model more accurately the spin decay during the ball flight.


To link the launcher design to the simulation, the initial ball speed was defined


by the rotation of the two launching wheels. In this specific model, the average


speed of the tangential component of the two wheels was taken to be the launch


forward speed of the ball, while the difference in the two wheel speeds was taken to


be the initial angular velocity. This permitted us to simulate the effect of different


wheel speeds, in which different combinations of wheel velocities produce different


spin states. Multiple launches were then simulated for several combinations of wheel


speeds in order to identify the different trajectories.


Two sets of simulations were considered. The first was to align the spin axis


to produce side-spin, where the ball would trajectory would be influenced by the


35


spin-induced lateral deflection. This provided insight into curved passes or shots. In


the second case, the spin axis was oriented to model topspin and backspin condi

tions, which affected the vertical motion of the ball, causing it to rise or dip more or


less rapidly in its trajectory. Through this comparison, the simulation was able to


determine how the launcher could be set up to deliver different training balls with


prescribed behavior.


We incorporated a full-pitch view into the MATLAB interface to view the simu

lated trajectories. The pitch size, half-way line, penalty boxes and goals were drawn


on the 3D plot, allowing the ball trajectory to be projected onto a model of the foot

ball field. This was helpful from a presentation perspective, but also for determining


if a simulated trajectory was within the anticipated workspace. Each trajectory was


terminated with a marker to facilitate comparison of the final end point of different


kicking attempts.


To improve the robustness of the simulation, event-based integration termination


criteria were used. The runge-kutta integration was automatically stopped when the


ball hit the ground, reached the maximum allowed altitude, or fell outside the field


of play. This stopped the numerical integration after the desired portion of the ball


flight and guaranteed that all trajectories were relevant to the football training use


case.


In summary, the MATLAB simulation tools were used as a bridge between simu

lation and hardware. They provided a platform to investigate effects of wheel speed,


spin direction and launching angle in a controlled setting before conducting repeated


hardware tests. In future project stages, the tools can also be used to define reference


trajectories, study experimentally measured trajectories, and aid software correction


of launcher parameters.


Simulation results are used to refine design variables (e.g., motor speed and launch


angle) in an iterative design process until predictable results are obtained.


36


Figure 3-7: Simulation results.

### **3.3 Control system and electronics**

#### **3.3.1 Hardware control setup**


The system control hardware was designed to deliver a safe power supply, motor


acceleration and ball feeding to the launcher. The hardware control system includes


the main launching motors, the aiming and feeding actuators, the microcontroller

based control system, and the external power electronics needed to provide various


levels of power to different components.


The main launcher system is comprised of a brushless DC (BLDC) motor (T

Motor AT4130 230KV) and a Hobbywing Xrotor Pro 50A electronic speed controller


(ESC). This is chosen because the BLDC motor is able to operate at high speed


and maintain smooth motion control, while the ESC provides throttle-stable speed


control. Because the launcher requires rapid acceleration of the wheels, and consistent


operating conditions for them, the BLDC-ESC combination is a viable option for fast


wheel actuation.


The overall system is powered from an AC-to-DC power supply that converts the


mains input of 220 V AC to 24 V DC. This is then used as the main power bus for the


electronic components. But not all devices need to operate at the same voltage. So,


extra power conversion is applied to low-voltage devices. In particular, the ESP-based


control board is supplied through a step-down converter, which reduces the voltage


from the main 24 V supply to the lower voltage required by the microcontroller. Other


37


Figure 3-8: Step-down converter and relay module used for voltage regulation and
switching of auxiliary actuators.


Figure 3-9: Solenoid actuator used in the ball dispensing mechanism.


low voltage components are also driven in a similar way, if needed. This approach


simplifies the power architecture by allowing a single source of main supply to be


connected to multiple subsystems that have different power requirements.


The ball dispensing mechanism also uses solenoids as actuators, which are also


powered from the same electrical system. They are powered by relay switching, which


helps in facilitating the release operation from the microcontroller without having to


directly drive the solenoids. This is necessary as the current being drawn by the


solenoids is greater than the recommended current output of the microcontroller.


So the relay module serves as an intermediary between the logic controller and the


dispenser.


A ball dispenser was designed to control the feeding of the ball into the launcher.


38


Figure 3-10: Overview of the ball dispenser mounted above the launcher structure.


Solenoids are used as a locking and releasing mechanism. Upon activation, the


solenoid activates the release mechanism which then lets one ball roll into the feeding


channel. This allows the ball feeding to be repeatable and the ball to be positioned


automatically before launch. In the experimental design, the dispenser was placed


above the launcher tube to allow the ball to fall through the feeding section.


The feeding mechanism was developed to place the ball in the right position for


launching. It has a structure that includes a feeding guide that keeps the ball in the


centre of the launcher and facilitates controlled feeding into the wheels. The feeder of


39


Figure 3-11: Side view of the feeder section and launcher entry path.


Figure 3-12: Motor-driven feeder mechanism used to position the ball before launch.


the prototype system employs a NEMA 17 stepper motor with a belt drive. The belt


is connected to a pusher that runs on an MGN12H linear rail. This enables controlled


linear movement of the ball towards the wheels. The linear rail helps achieve better


alignment and repeatability, while the belt-driven pusher offers a simple and compact


mechanism for feeding balls. The ball was also supported by other mechanical features


and guide rods. In the present prototype, the feeder was mounted in the main frame,


between the two launching wheels. This ensured that the ball entered the wheel


contact area from the same location.


40


Figure 3-13: Top view of the feeder channel and ball-guiding structure.


In terms of control, the hardware setup can be separated into several blocks. The


first layer is power conversion and distribution, which supplies the voltages to motors,


control components and actuators. The second layer is actuation, which provides the


BLDC motor and ESC for spinning the wheel, and the solenoid release for the ball.


Finally, the logical layer is the ESP-controller that triggers relay, feeder, and other


time-based actions. This approach enhances modularity and aids in troubleshooting,


as each part can be tested independently of the rest of the system.


In summary, the actual control hardware was designed to facilitate reliable launcher


operation, ball release, and integration of relevant subsystems. Using a 24 V main


source, onboard voltage conversion, ESC motor control and relay-based solenoid ac

tivation created a foundation for advanced development of autonomous aiming and


launching capabilities. To provide closed-loop speed control for the launcher wheels


and thus repeatable speed, an absolute magnetic encoder was also integrated into the


drivetrain; the encoder and mount are shown in Figure 3-14.


41


(a) Encoder module. (b) Mounting/assembly.


Figure 3-14: Absolute magnetic encoder used for closed-loop sensing.


For controlling the 2 DOF gimbal axes, NEMA 23 stepper motors are used. Worm


gears are used to reduce back-driving. An Arduino Uno controls the stepper motors,


which are connected to the Jetson. The chosen components used to drive the axes: the


motors (Figure 3-15a) allow repeatable step-and-hold movement while the reducers


(Figure 3-15b) provide greater output torque (to hold the platform at a given angle)


and reduce back-driving.


(a) Motors. (b) Reducers.


Figure 3-15: Axis motors and reducers used for platform actuation.


42


# **Chapter 4** **System Testing and Training**

### **4.1 Experimental Environment and 3D Projection**

The physical experiment room is a garage arena of dimension 6230 mm (X) _×_


3050 mm (Y) _×_ 2950 mm (Z). To be able to fully observe the environment, four


Hikvision DS-E12 USB cameras were fixed in place close to the ceiling. Camera


synchronisation was achieved with a software flashlight "sync marker" protocol, and


all camera streams were synchronised to the same frame. The new indoor testing


setup with the ball launcher installed and aligned to the calibration camera network


is shown in figure 4-1.


We developed a two-phase calibration process to map 2D image measurements into


a world frame. First, intrinsic calibration at 1280 _×_ 720 resolution was done with


ChArUco boards, resulting in a reprojection error of 2-8 pixels. Second, extrinsic


calibration used a 24-AprilTag wall and solved for the pose of each camera using


Perspective-n-Point (PnP) optimisation with iterative refinement. This produced


a reprojection residual error of 3-7 pixels in the arena. Figure 4-2 shows example


simultaneous views used for defining the common world frame and visually confirming


the quality of the calibration before performing any detection and triangulation.


Once calibrated, 2D multi-camera detections are fused into a 3D point. For 3D


object localization, we employ a Direct Linear Transform (DLT) based triangulation


(using Singular Value Decomposition (SVD) to solve it). This process takes the set


43


Figure 4-1: Ball launcher installed in the completed indoor testing setup.


Figure 4-2: Live multi-camera views used to establish the common world frame and
assess calibration quality.


44


of synchronized 2D image plane data points and generates the best-fit 3D point in


the world frame, allowing for tasks like trajectory generation and targeting. One


possibility for a 3D projection is demonstrated in Figure 4-3.


Figure 4-3: Example result of projecting synchronized 2D detections into the 3D
world frame.

### **4.2 Ball and Pose Detection Systems**


To track specific body parts in real-time we need to have accurate object detection.


Our human pose estimation pipeline uses the MMPose framework, and a COCO 17

keypoint pose skeleton model to target the right knee, right hip and left shoulder of


the athlete.


Regarding ball detection, we noticed a large dataset skew in the existing open

source ball tracking models, which are mainly biased towards match footage with wide


shots. In response, we created a new _ProxiBall_ dataset comprising 18,027 selected


frames of high-speed, close-up soccer ball images with extreme motion blur and scale


45


variation. This dataset was used to train a YOLOv11s object detector.

### **4.3 User Interface and Voice Control Integration**


The user interface provides a means to interact with the autonomous system. The


speech recognition feature of the user interface is currently using a small offline model


called a Speech-to-Text (SST) model from VOSK. But we are in the process of switch

ing to using the OpenAI Whisper API to transcribe audio. The transcription will


then be fed to a Large Language Model (LLM) with carefully crafted prompts to


intelligently understand text and compare the text to the system-ordered commands,


enabling much more conversational user input for system control.

### **4.4 Low-Level Hardware Control and Integration**


Bridging the gap between the high-level Python AI solver and the physical Ball


Launching Machine (BLM) is an ESP32 microcontroller. The ESP32 runs a Blue

tooth Low Energy (BLE) server to wirelessly accept string-based commands (e.g.,


`set` `v` `h` `wl` `wr`, `shoot`, `reload` ) from the master system or mobile phone.


The ESP32 controls four major actuators:


  - **Aiming** **(Pan/Tilt):** The vertical (pitch) and horizontal (yaw) angles are


controlled by stepper motors, and are powered by the `AccelStepper` library for


angular control.


  - **Propery** **and** **Ball** **Shooting:** The two Brushless DC (BLDC) wheel motors


are driven by Electronic Speed Controllers (ESCs) and microsecond PWM sig

nal. RPM feedback is provided via the `ESP32Encoder` library (from magnetic


encoders, 1000 PPR and 2000 PPR on the left and right side, respectively).


  - **Safe** **Guarding:** The ball feeder servo is hardcoded with a safety gate  - the


microcontroller will not drive the ball feed to place a ball between the wheels


46


until the current operating RPM of the motor is greater than 400 RPM, ensuring


the motors are not jammed.

### **4.5 AI Aiming and Reinforcement Learning Training**

#### **4.5.1 AI Aiming and Reinforcement Learning Training**


The AI aiming module is a reinforcement learning problem where the launcher is


trained to reduce the gap between the target point and the ball’s point of impact. In


our system, the perception system feeds the three-dimensional information of the ball


and the target, which is the body joint that the ball will collide with, to the control


system, while the control system processes the aiming and launching commands via


an ESP32 board. As such, the launcher provides a closed-loop learning system that


incorporates visual feedback for future shots.


We treated the aiming task as a continuous-control problem. On each launch,


the state vector consists of the target coordinates, the global launcher orientation,


the current wheel speeds, and the error provided by the previous launches. Since the


action is continuous, the learner provides corrections for the horizontal and vertical


aiming, as well as the rotational speed of the left and right wheels. This problem is well


suited to actor-critic methods for reinforcement learning, such as Deep Deterministic


Policy Gradient (DDPG) and Proximal Policy Optimization (PPO), which have been


demonstrated to work for continuous-control tasks [22,23,46].


More specifically, the action vector is of the form


_𝑎𝑡_ = [∆ _𝜓𝑡,_ ∆ _𝜃𝑡,_ ∆RPM _𝐿,𝑡,_ ∆RPM _𝑅,𝑡_ ] _,_ (4.1)


where ∆ _𝜓𝑡_ and ∆ _𝜃𝑡_ represent corrections for horizontal and vertical pointing and


∆RPM _𝐿,𝑡_ and ∆RPM _𝑅,𝑡_ represent corrections for the left and right wheel rotational


speeds of the launching motors. This permits the policy to correct the positioning of


the launcher, and also the ball speed and spin due to varying wheel speed.


The reward definition was designed to reward successful targeting without com

47


promising safe mechanical operation. For each launch, the multi-camera system mea

sures the three-dimensional position of the ball landing or interception point and this


position is compared to the chosen target joint position. A basic reward definition is


_𝑟𝑡_ = _−_ ⃦⃦ **p** land _𝑡_ _−_ **p** [target] _𝑡_ ⃦⃦2 _[−]_ _[𝜆]_ [1] _[𝑃]_ [unsafe] _[ −]_ _[𝜆]_ [2] _[𝑃]_ [jam] _[,]_ (4.2)


where **p** [land] _𝑡_ is the ball position at match time, **p** [target] _𝑡_ is the target position, and


the penalty terms punish unsafe launch positions and feeder failures. So the policy is


rewarded for achieving a small Euclidean miss distance, while also taking into account


the actuator and safety constraints.


We tested two reinforcement learning algorithms. The former was chosen because


it uses deterministic policy gradients, and is designed specifically for continuous action


spaces [22, 46]. This is well matched for learning smooth changes in pan, tilt and


forward speed. PPO was also considered because of the stability of the policy updates


afforded by the clipped surrogate objective, and the balance between simplicity and


empirical performance it achieves [23]. DDPG is a generally a better choice if sample


efficiency is a priority, while PPO is a better choice if stability and simplicity are


priorities.


The training was performed in two phases. The first stage involved training the


policy in the previously described projectile and spin-aware model. The simulator


was used to produce target locations, initial launcher conditions, and the expected


ball trajectory behavior for each combination of launcher conditions. To prevent


over-specialization to an ideal simulation environment, we use the tool of domain

randomization, varying the drag-related function, spin decay, wheel slip, target

detection noise, and the actuation delay. This approach is inspired by sim-to-real


transfer learning, in which randomising simulation makes the real system appear as


just another variation of the training environment [47].


Next, the policy was tuned using the real experimental bidirectional launcher. A


single episode involved the launcher picking a target joint, calculating the state of the


system, launching a single ball, measuring the landing position error, and learning


48


from the experience. The training in the real world is particularly important due to


effects that are difficult to model in the physical system, including variation in wheel

to-ball contact, vibration, backlash in the aiming mechanism, and ball aerodynamics.


After a few episodes, the RL agent can learn to compensate for this.


Due to the interaction with hardware, safe exploration is needed. The policy


thus had software constraints on maximum pan/tilt and RPM. The feeder safety


checks described above were also enabled during training so that the ball would not


be launched unless the launcher wheels were operating at a suitable speed. This


prevented learning from invalidating safe operation of the mechanical system.


Overall, the reinforcement learning module extends the launcher from an open

loop trajectory generator into an adaptive targeting system. Through the combi

nation of visual feedback, continuous control and policy iteration, the launcher can


train itself to minimise misalignment error and adapt to the mismatch between the


ball’s trajectory and the physics-based estimates of the ball’s flight. Such learning


is similar to previous reinforcement-learning results in robotic control, robot-soccer,


and other tasks where the agent improves its performance through interaction with


the environment [44].


49


# **Chapter 5** **Results and Discussions**

### **5.1 Results and Discussions**

The results of the experiments conducted with the multifunctional autonomous ball


launcher are presented in this chapter and the performance of the key subsystems


is discussed. We will address four main points: the performance of the vision sub

systems, the responsiveness of the mechanism, the operation of the reinforcement

learning-driven aiming system, and the impact and limitations of the present proto

type. Given the complexities of this system, which involves computer vision, motion


control, trajectory simulation, and hardware actuation, the results are organized on


a subsystem basis prior to discussing the autonomous behavior.

#### **5.1.1 Subsystem Performance Evaluation**


The initial round of tests considered the vision and target localization subsystems,


as the final aiming performance depends on detecting the target ball. In particular,


the YOLOv11s detector with the ProxiBall dataset as input produced a mAP@50 of


0.9786 and recall of 0.9551. This suggests the new dataset was well aligned with the


actual operational environment of the launcher, particularly with small, high-speed,


blurred balls. As compared to datasets of football games in general, the domain

specific dataset enabled better generalisation for small indoor practice environments,


50


in which the ball may be seen close to the camera and in poor lighting conditions.


We also tested the three-dimensional ball localization subsystem using static and


dynamic ground-truth data. The results from the initial static tests showed a perma

nent offset in the reconstructed coordinates in the vertical direction, resulting from the


geometry of the ceiling-mounted cameras. This post-calibration decreased the average


3D localization error for the ball from 150.77 mm to 95.17 mm. This improvement


was achieved by geometric post-calibration, and it shows that the implementation of


multi-camera triangulation is more practical after geometric post-calibration.


The accuracy of pose estimation was evaluated for some athlete body joints con

sidered as potential targets for aiming, in particular the right knee, right hip and


left shoulder. The mean 3D errors were 110.03 mm, 150.38 mm, and 164.38 mm,


respectively. While these errors are not trivial, they are still acceptable for localized


body part aiming in football training, particularly if the goal is to train for reaction,


receiving, and control, as opposed to robotic accuracy on the millimeter scale.


The pose-target localizations were also evaluated by comparing the reconstructed


joint coordinates to reference targets (ground truth) points in 3D at several locations


in the arena. Figure 5-1 illustrates the matches of the left shoulder, right hip, and right


knee. The estimated points preserve the spatial relationships of the references; hence,


the target joints are consistently represented in 3D; the remaining offsets are primarily


due to model calibration, pose-estimation error, and small mechanical aiming offsets.


In general, the observed closeness of matched points justifies the use of closed-loop


auto-aiming using visually perceived body targets.


Overall, the above results indicate that the perception subsystem presently sup

plies adequate information for reliable auto-aiming. The vision system may not be


perfect but its accuracy is already sufficient to support the main purpose of the


launcher: shooting balls towards body-aligned targets.

#### **5.1.2 Responsiveness of the mechanical and overall system**


The second part of the focusing process involved testing the effectiveness of trans

lating control commands into physical launcher action. In the current system, the


51


Figure 5-1: 3D ground-truth vs. estimated target coordinates for selected body joints
during auto-aiming validation.


ESP32 controller is the low-level interface between AI software and the mechanical


components, which control the aiming motors, wheel speed, and the ball-feeder. From


the test results, the control firmware responded promptly to command updates, and


the subsystems of the launcher were in stable coordination for multiple launching


repetitions.


Of particular note is the safety interlock on the ball feeder. In initial tests, the


ball-feeding sequence could cause unstable launches or jam the feeder if the launch


wheels did not spin at the required speed. To eliminate this possibility, the ball feeder


was precluded from beginning operation until the wheel rotational speed reaches


400 RPM. This condition has successfully prevented jamming of the feeder in repeated


experiments, suggesting that the safety interlock improved the repeatability of the


load cycle.


Emergency stop and gating times were also tested. Software-based gating and


52


emergency stops have latch times less than 100 ms. This is essential when the


launcher includes fast-rotating wheels, feeders and stepper-controlled aiming axes.


This enabled a practical degree of safety for laboratory testing and indoor experi

mentation.


In terms of the mechanical structure, responsiveness was affected by the firmware


of the launcher and also by the backlash of the aiming reducer, wheel inertia and


the feeder positioning mechanism. Software compensation optimised aiming accu

racy, and the feeder guide significantly reduced feed variation. While the prototype


contained some mechanical flexibility and vibration, the overall system was able to


repeat launch actions with a level of repeatability sufficient for experimental research.


In general, the response test results suggest that the control and actuation sub

systems are fast enough to enable autonomous operation. The hardware was not only


a proof of concept, but was also an integrated electro-mechanical system that was


able to receive a target, safely prepare the launcher for action and perform repeatable


launch cycles.


53


# **Appendix A** **Figures**

Figure A-1: First constructed testing system.


54


Figure A-2: Power Source 24V.


55


# **Bibliography**


[1] Y. Li. _Motion Analysis of Soccer Ball:_ _Dynamics Modeling,_ _Optimization Design_
_and_ _Virtual_ _Simulation_ . Springer, 2022.


[2] K. Bray and D. Kerwin. Modelling the flight of a soccer ball in a direct free kick.
_Journal_ _of_ _Sports_ _Sciences_, 21(2):75–85, 2003.


[3] P. Neilson, R. Jones, D. Kerr, and C. Sumpter. An image recognition system for
the measurement of soccer ball spin characteristics. _Measurement_ _Science_ _and_
_Technology_, 15(11):2239–2247, 2004.


[4] J. E. Goff, J. Kelley, C. M. Hobson, K. Seo, T. Asai, and S. B. Choppin. Creating drag and lift curves from soccer trajectories. _European_ _Journal_ _of_ _Physics_,
38(4):044003, 2017.


[5] J. E. Goff and M. J. Carré. Trajectory analysis of a soccer ball. _American Journal_
_of_ _Physics_, 77(11):1020–1027, 2009.


[6] I. Negron, J. Perdomo, R. Saco, A. Sinanan, and S. Tosunoglu. Skillcourt autonomous ball launcher.


[7] E. G. S. Cole and A. M. Sherman. Lightweight materials for automotive applications.


[8] D. P. Manning and C. Jones. The effect of roughness, poor polish, water, oil and
ice on underfoot friction: current safety footwear solings are less slip resistant
than microcellular polyurethane, 2001.


[9] M. Alberto, M. Iliut, M. K. Pitchan, J. Behnsen, and A. Vijayaraghavan. Highgrip and hard-wearing graphene reinforced polyurethane coatings. _Composites_
_Part_ _B:_ _Engineering_, 213, May 2021.


[10] I. Raghuram, G. Jaya Surya, P. Joseph, C. Vijaya, K. Rao, and B. Susmitha.
Fabrication of soccer and cricket ball launching machine. _International_ _Journal_
_of_ _Engineering_ _and_ _Management_ _Research_, 2023.


[11] M. A. Kattimani, A. Raza, S. Ameer, and R. Scholar. Design and fabrication of
cricket ball launching machine, 2019.


56


[12] A. Singh, A. Farzaneh, J. Grewal, M. Tran, Z. Lin, and T. Li. Kickpro-proposal,
2023.


[13] Y. Li. Motion analysis of soccer ball dynamics modeling, optimization design and
virtual simulation (springer briefs in applied sciences and technology). Online
resource.


[14] S. Barber and M. Carré. Computational fluid dynamics for sport simulation. In
_Computational Fluid Dynamics for Sport Simulation_, volume 72 of _Lecture Notes_
_in_ _Computational_ _Science_ _and_ _Engineering_ . Springer Berlin Heidelberg, Berlin,
Heidelberg, 2009.


[15] E. Barros and J. Guilherme. This autonomous soccer robot can aim, shoot, and
score. NVIDIA Developer Blog, March 2025. Accessed: 2025-03-09.


[16] H. Lin and Y.-C. Huang. Ball trajectory tracking and prediction for a ping-pong
robotprogram, 2019.


[17] A. Al-Omari, H. B. Schüttler, J. Arnold, and T. Taha. Solving nonlinear systems of first order ordinary differential equations using a galerkin finite element
method. _IEEE_ _Access_, 1:408–417, 2013.


[18] P. Neilson, R. Jones, D. Kerr, and C. Sumpter. An image recognition system for
the measurement of soccer ball spin characteristics. _Measurement_ _Science_ _and_
_Technology_, 15(11):2239–2247, 2004.


[19] Richard A. Schmidt and Timothy D. Lee. _Motor_ _Control_ _and_ _Learning:_ _A_
_Behavioral_ _Emphasis_ . Human Kinetics, 5th edition, 2011.


[20] A. Mark Williams and Paul R. Ford. Expertise and skill acquisition in sport.
_International_ _Review_ _of_ _Sport_ _and_ _Exercise_ _Psychology_, 1(1):4–18, 2008.


[21] Bruno Siciliano, Lorenzo Sciavicco, Luigi Villani, and Giuseppe Oriolo. _Robotics:_
_Modelling,_ _Planning_ _and_ _Control_ . Springer, 2016.


[22] Timothy P. Lillicrap, Jonathan J. Hunt, Alexander Pritzel, and et al. Continuous
control with deep reinforcement learning. _arXiv preprint arXiv:1509.02971_, 2015.


[23] John Schulman, Filip Wolski, Prafulla Dhariwal, Alec Radford, and Oleg Klimov.
Proximal policy optimization algorithms. _arXiv preprint arXiv:1707.06347_, 2017.


[24] R. Rein and D. Memmert. Big data and tactical analysis in elite soccer: future
challenges and opportunities. _SpringerPlus_, 5(1):1410, 2016.


[25] Takeshi Asai, Kazuya Seo, Osamu Kobayashi, and Ryuichi Sakashita. Fundamental aerodynamics of the soccer ball. _Sports Engineering_, 10(2):101–110, 2007.


[26] Sarah Barber, Steve J. Haake, and Matt J. Carré. Using cfd to understand the
effects of seam geometry on soccer ball aerodynamics. In E. F. Moritz and S. J.
Haake, editors, _The_ _Engineering_ _of_ _Sport_ _6_, pages 127–132. Springer, 2006.


57


[27] Ken Bray and David G. Kerwin. Modelling the flight of a soccer ball in a direct
free kick. _Journal_ _of_ _Sports_ _Sciences_, 21(2):75–85, 2003.


[28] Matt J. Carré, Takeshi Asai, T. Akatsuka, and Steve J. Haake. The curve kick
of a football ii: Flight through the air. _Sports_ _Engineering_, 5(4):193–200, 2002.


[29] John Eric Goff and Matt J. Carré. Trajectory analysis of a soccer ball. _American_
_Journal_ _of_ _Physics_, 77(11):1020–1027, 2009.


[30] John Eric Goff, John Kelley, Chad M. Hobson, Kazuya Seo, Takeshi Asai, and
S. B. Choppin. Creating drag and lift curves from soccer trajectories. _European_
_Journal_ _of_ _Physics_, 38(4):044003, 2017.


[31] M. A. Passmore, S. Tuplin, A. Spencer, and R. Jones. Experimental studies
of the aerodynamics of spinning and stationary footballs. _Proceedings_ _of_ _the_
_Institution_ _of_ _Mechanical_ _Engineers,_ _Part_ _C:_ _Journal_ _of_ _Mechanical_ _Engineering_
_Science_, 222(2):195–205, 2008.


[32] Luca Oggiano and Lars Sætran. Aerodynamics of modern soccer balls. _Procedia_
_Engineering_, 2(2):2473–2479, 2010.


[33] Ying Li. _Motion_ _Analysis_ _of_ _Soccer_ _Ball:_ _Dynamics_ _Modeling,_ _Optimization_
_Design_ _and_ _Virtual_ _Simulation_ . Springer, Singapore, 2022.


[34] João G. Melo, Felipe B. Martins, Lucas Cavalcanti, Roberto Fernandes, Victor
Araújo, Riei Joaquim, João Guilherme Monteiro, and Edna Barros. Towards an
autonomous RoboCup small size league robot. In _2022_ _Latin_ _American_ _Robotics_
_Symposium_ _(LARS),_ _2022_ _Brazilian_ _Symposium_ _on_ _Robotics_ _(SBR),_ _and_ _2022_
_Workshop_ _on_ _Robotics_ _in_ _Education_ _(WRE)_, pages 1–6, 2022.


[35] João G. Melo and Edna Barros. An embedded monocular vision approach for
ground-aware objects detection and position estimation. In _RoboCup 2022:_ _Robot_
_World_ _Cup_ _XXV_, volume 13561 of _Lecture_ _Notes_ _in_ _Computer_ _Science_, pages
100–111. Springer, Cham, 2023.


[36] Victor Araújo, Felipe Martins, Roberto Fernandes, and Edna Barros. A
telemetry-based PI tuning strategy for low-level control of an omnidirectional
mobile robot. In _RoboCup_ _2021:_ _Robot_ _World_ _Cup_ _XXIV_, volume 13132 of _Lec-_
_ture_ _Notes_ _in_ _Computer_ _Science_, pages 189–201. Springer, Cham, 2022.


[37] Alexander Gabel, Tanja Heuer, Ina Schiering, and Reinhard Gerndt. Jetson,
where is the ball? using neural networks for ball detection at robocup 2017.
In _RoboCup_ _2018:_ _Robot_ _World_ _Cup_ _XXII_, volume 11374 of _Lecture_ _Notes_ _in_
_Artificial_ _Intelligence_, pages 181–192. Springer, Cham, 2019.


[38] António J. R. Neves, Armando J. Pinho, Daniel A. Martins, and Bernardo
Cunha. An efficient omnidirectional vision system for soccer robots: From calibration to object detection. _Mechatronics_, 21(2):399–410, 2011.


58


[39] Anton Kurniawan Mulya, Fernando Ardilla, and Dadet Pramadihanto. Ball
tracking and goal detection for middle size soccer robot using omnidirectional
camera. In _2016_ _International_ _Electronics_ _Symposium_ _(IES)_, pages 432–437,
2016.


[40] Márton Szemenyei and Vladimir Estivill-Castro. Fully neural object detection
solutions for robot soccer. _Neural_ _Computing_ _and_ _Applications_, 34:21419–21432,
2022.


[41] Handaru Jati, Nur Alif Ilyasa, and Dhanapal Durai Dominic. Enhancing humanoid robot soccer ball tracking, goal alignment, and robot avoidance using
YOLO-NAS. _Journal_ _of_ _Robotics_ _and_ _Control_ _(JRC)_, 5(3):829–838, 2024.


[42] Seth Hutchinson, Gregory D. Hager, and Peter I. Corke. A tutorial on visual
servo control. _IEEE_ _Transactions_ _on_ _Robotics_ _and_ _Automation_, 12(5):651–670,
1996.


[43] Chen Tang, Ben Abbatematteo, Jiaheng Hu, Rohan Chandra, Roberto MartínMartín, and Peter Stone. Deep reinforcement learning for robotics: A survey
of real-world successes. _Annual_ _Review_ _of_ _Control,_ _Robotics,_ _and_ _Autonomous_
_Systems_, 8:153–188, 2025.


[44] Isaac Jesus da Silva, Danilo Hernani Perico, Thiago Pedro Donadon Homem, and
Reinaldo Augusto da Costa Bianchi. Deep reinforcement learning for a humanoid
robot soccer player. _Journal_ _of_ _Intelligent_ _&_ _Robotic_ _Systems_, 102:69, 2021.


[45] Ping-Huan Kuo, Wei-Cyuan Yang, Po-Wei Hsu, and Kuan-Lin Chen. Intelligent proximal-policy-optimization-based decision-making system for humanoid
robots. _Advanced_ _Engineering_ _Informatics_, 56:102009, 2023.


[46] David Silver, Guy Lever, Nicolas Heess, Thomas Degris, Daan Wierstra, and
Martin Riedmiller. Deterministic policy gradient algorithms. In _Proceedings_ _of_
_the 31st International Conference on Machine Learning_, volume 32 of _Proceedings_
_of_ _Machine_ _Learning_ _Research_, pages 387–395, 2014.


[47] Joshua Tobin, Rachel Fong, Alex Ray, Jonas Schneider, Wojciech Zaremba, and
Pieter Abbeel. Domain randomization for transferring deep neural networks from
simulation to the real world. In _2017_ _IEEE/RSJ_ _International_ _Conference_ _on_
_Intelligent_ _Robots_ _and_ _Systems_ _(IROS)_, pages 23–30, 2017.


[48] Martin A. Fischler and Robert C. Bolles. Random sample consensus: A paradigm
for model fitting with applications to image analysis and automated cartography.
_Communications_ _of_ _the_ _ACM_, 24(6):381–395, 1981.


[49] Joseph Redmon, Santosh Divvala, Ross Girshick, and Ali Farhadi. You only look
once: Unified, real-time object detection. In _Proceedings_ _of_ _the_ _IEEE_ _Confer-_
_ence_ _on_ _Computer_ _Vision_ _and_ _Pattern_ _Recognition_ _(CVPR)_, pages 779–788, Las
Vegas, NV, 2016.


59


[50] Zhe Cao, Gines Hidalgo, Tomas Simon, Shih-En Wei, and Yaser Sheikh. Openpose: Realtime multi-person 2d pose estimation using part affinity fields. _IEEE_
_Transactions on Pattern Analysis and Machine Intelligence_, 43(1):172–186, 2021.


[51] Tsung-Yi Lin, Michael Maire, Serge Belongie, James Hays, Pietro Perona, Deva
Ramanan, Piotr Dollár, and C. Lawrence Zitnick. Microsoft COCO: Common
objects in context. In _Proceedings_ _of_ _the_ _European_ _Conference_ _on_ _Computer_
_Vision_ _(ECCV)_, pages 740–755, Zurich, Switzerland, 2014.


[52] Ke Sun, Bin Xiao, Dong Liu, and Jingdong Wang. Deep high-resolution representation learning for visual recognition. _IEEE Transactions on Pattern Analysis_
_and_ _Machine_ _Intelligence_, 43(10):3349–3364, 2019.


[53] J. L. Meriam and L. G. Kraige. _Engineering_ _Mechanics:_ _Dynamics_ . Wiley,
Hoboken, NJ, 7 edition, 2012.


[54] M. Tim Jones. _Embedded_ _Systems_ _Design_ _with_ _the_ _Atmel_ _AVR_ _Microcontroller_ .
Cengage Learning, Boston, MA, 2016.


[55] International Electrotechnical Commission. IEC 62061: Safety of machinery functional safety of safety-related control systems, 2021.


[56] International Organization for Standardization. Iso 10218-1: Robots and robotic
devices   - safety requirements for industrial robots   - part 1: Robots, 2011.


[57] International Organization for Standardization. Iso 12100: Safety of machinery

 - general principles for design, 2011.


60


