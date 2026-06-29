%% nuthesis.cls --Nazarbayev University SEDS/ECE Thesis Class
%% Modelled on the formatting of approved NU PhD/MSc theses
\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{nuthesis}[2026/03/28 Nazarbayev University Thesis Class]

\LoadClass[12pt,a4paper,oneside]{report}

%% ---------- PACKAGES ----------
\RequirePackage[utf8]{inputenc}
\RequirePackage[T1]{fontenc}
\RequirePackage{mathptmx}                 % Times New Roman clone
\RequirePackage[left=2.5cm,right=2.5cm,top=2.5cm,bottom=2.5cm,headheight=15pt]{geometry}
\RequirePackage{setspace}                 % \doublespacing
\RequirePackage{titlesec}                 % heading formatting
\RequirePackage{titletoc}                 % TOC formatting
\RequirePackage{fancyhdr}                 % headers/footers
\RequirePackage{graphicx}
\RequirePackage{caption}
\RequirePackage{subcaption}
\RequirePackage{booktabs}
\RequirePackage{tabularx}
\RequirePackage{longtable}
\RequirePackage{amsmath,amssymb}
\RequirePackage[hidelinks]{hyperref}
\RequirePackage{bookmark}
\RequirePackage{enumitem}
\RequirePackage{float}
\RequirePackage{xcolor}
\RequirePackage{listings}
\lstset{
  basicstyle=\ttfamily\small,
  breaklines=true,
  breakatwhitespace=true,
  breakautoindent=true,
  postbreak=\mbox{\textcolor{gray}{$\hookrightarrow$}\space},
  frame=single,
  xleftmargin=0.5cm,
  xrightmargin=0.5cm,
  columns=flexible
}
\RequirePackage{url}
\RequirePackage[numbers]{natbib}          % numeric citations [1]
\renewcommand{\bibname}{Bibliography/References}
\RequirePackage{etoolbox}
\RequirePackage{tocloft}
\RequirePackage{framed}                  % fine-tune TOC/LOT/LOF
\RequirePackage[normalem]{ulem}          % \uline for underlined headings

%% ---------- SPACING ----------
\doublespacing
\setlength{\parindent}{1.25cm}
\setlength{\parskip}{0pt}

%% ---------- PAGE STYLE ----------
% Page numbers centered at TOP (12pt font), no running headers
\pagestyle{fancy}
\fancyhf{}
\fancyhead[C]{\fontsize{12}{14}\selectfont\thepage}
\renewcommand{\headrulewidth}{0pt}
\renewcommand{\footrulewidth}{0pt}

% Plain style for chapter opening pages
\fancypagestyle{plain}{%
  \fancyhf{}%
  \fancyhead[C]{\fontsize{12}{14}\selectfont\thepage}%
  \renewcommand{\headrulewidth}{0pt}%
}

% Chapter marks: update running header for both regular chapters and appendices
\renewcommand{\chaptermark}[1]{%
  \markboth{\MakeUppercase{\thechapter.\ #1}}{}%
}

%% ---------- CHAPTER / SECTION HEADINGS ----------
% Chapter: "CHAPTER 1.  INTRODUCTION"  centred, bold, 16pt
\titleformat{\chapter}[display]
  {\normalfont\fontsize{16}{19}\bfseries\centering}
  {\MakeUppercase{\chaptertitlename}\ \thechapter.}
  {0.5em}
  {\MakeUppercase}
\titlespacing*{\chapter}{0pt}{-20pt}{24pt}

% Section: "1.1 Motivation and Problem Statement" --bold, 14pt
\titleformat{\section}
  {\normalfont\fontsize{14}{17}\bfseries}
  {\thesection}
  {1em}
  {}
\titlespacing*{\section}{0pt}{12pt}{6pt}

% Subsection: "1.1.1 Title" --bold italic, 12pt
\titleformat{\subsection}
  {\normalfont\fontsize{12}{14}\bfseries\itshape}
  {\thesubsection}
  {1em}
  {}
\titlespacing*{\subsection}{0pt}{12pt}{6pt}

% Subsubsection: for appendix sub-headings --bold, underlined, 14pt
\titleformat{\subsubsection}
  {\normalfont\fontsize{14}{17}\bfseries}
  {\thesubsubsection}
  {1em}
  {\uline}
\titlespacing*{\subsubsection}{0pt}{12pt}{6pt}

%% ---------- FIGURE AND TABLE CAPTIONS ----------
% "Figure 3.1. Caption text" --bold italic, 12pt, centred
\captionsetup[figure]{labelsep=period, font={bf,it}, justification=centering, skip=6pt}
\captionsetup[table]{labelsep=period, font={bf,it}, justification=centering, skip=6pt, position=top}

%% ---------- TOC FORMATTING ----------
\renewcommand{\contentsname}{TABLE OF CONTENTS}
\renewcommand{\listtablename}{LIST OF TABLES}
\renewcommand{\listfigurename}{LIST OF FIGURES}

% TOC title: bold, 16pt, centered
\renewcommand{\cfttoctitlefont}{\normalfont\fontsize{16}{19}\bfseries\centering}
\renewcommand{\cftlottitlefont}{\normalfont\fontsize{16}{19}\bfseries\centering}
\renewcommand{\cftloftitlefont}{\normalfont\fontsize{16}{19}\bfseries\centering}

% Make chapter entries bold, 12pt
\renewcommand{\cftchapfont}{\normalfont\fontsize{12}{14}\bfseries}
\renewcommand{\cftchappagefont}{\normalfont\fontsize{12}{14}\bfseries}

% Make section entries regular (not bold), 12pt
\renewcommand{\cftsecfont}{\normalfont\fontsize{12}{14}}
\renewcommand{\cftsecpagefont}{\normalfont\fontsize{12}{14}}

% Equation numbering per chapter: (1.1), (1.2), ...
\numberwithin{equation}{chapter}
\numberwithin{figure}{chapter}
\numberwithin{table}{chapter}

%% ---------- FRONT MATTER COMMANDS ----------
% Unnumbered chapter that appears in TOC and sets mark
\newcommand{\frontchapter}[1]{%
  \cleardoublepage
  \phantomsection
  \addcontentsline{toc}{chapter}{\texorpdfstring{\MakeUppercase{#1}}{#1}}%
  \markboth{#1}{#1}%
  \begin{center}
    {\fontsize{16}{19}\bfseries\MakeUppercase{#1}\par}
  \end{center}
  \vspace{12pt}
}

%% ---------- COVER PAGE ----------
\newcommand{\thesistitle}{}
\newcommand{\thesisauthor}{}
\newcommand{\thesisdegree}{}
\newcommand{\thesisdepartment}{}
\newcommand{\thesisschool}{}
\newcommand{\thesissupervisor}{}
\newcommand{\thesiscosupervisor}{}
\newcommand{\thesisdate}{}

\renewcommand{\title}[1]{\renewcommand{\thesistitle}{#1}}
\renewcommand{\author}[1]{\renewcommand{\thesisauthor}{#1}}
\newcommand{\degree}[1]{\renewcommand{\thesisdegree}{#1}}
\newcommand{\department}[1]{\renewcommand{\thesisdepartment}{#1}}
\newcommand{\school}[1]{\renewcommand{\thesisschool}{#1}}
\newcommand{\supervisor}[1]{\renewcommand{\thesissupervisor}{#1}}
\newcommand{\cosupervisor}[1]{\renewcommand{\thesiscosupervisor}{#1}}
\renewcommand{\date}[1]{\renewcommand{\thesisdate}{#1}}

\newcommand{\makecover}{%
  \thispagestyle{empty}
  \begin{center}
    \vspace*{1.5cm}
    {\fontsize{16}{19}\bfseries\MakeUppercase{\thesistitle}\par}
    \vspace{2cm}
    {by\par}
    \vspace{0.5cm}
    {\fontsize{15}{18}\bfseries\thesisauthor\par}
    \vspace{1.5cm}
    {\fontsize{15}{18}\bfseries Submitted in fulfilment of the requirements for the degree of\par}
    \vspace{0.3cm}
    {\fontsize{15}{18}\thesisdegree\par}
    \vspace{1.5cm}
    % NU logo
    \includegraphics[width=4cm]{figures/nu_logo}\\[0.4cm]
    {\fontsize{15}{18}\bfseries\thesisschool\par}
    {\fontsize{15}{18}\bfseries\thesisdepartment\par}
    {\fontsize{15}{18}\normalfont Nazarbayev University\par}
    {\fontsize{15}{18}\normalfont 53 Kabanbay Batyr Avenue\par}
    {\fontsize{15}{18}\normalfont Astana, Kazakhstan, 010000\par}
    \vspace{0.8cm}
    {\fontsize{15}{18}\selectfont\textbf{Supervisor:} \thesissupervisor\par}
    \ifx\thesiscosupervisor\empty\else
      {\fontsize{15}{18}\selectfont\textbf{Co-supervisor:} \thesiscosupervisor\par}
    \fi
    \vfill
    {\fontsize{15}{18}\bfseries\thesisdate\par}
  \end{center}
  \clearpage
}

\endinput
