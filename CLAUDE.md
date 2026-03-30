# Foraging — Project Overview
A Unity-based 3D game built for psychology research on **feature-based reward learning** in naturalistic environments. Participants control an avatar navigating a virtual landscape, harvesting trees to obtain rewards. The core research question is how participants learn an underlying reward function defined over continuous tree attributes.

This is a **research tool first, game second**. Design decisions prioritize ecological validity, perceptual clarity of tree attributes, and unambiguous reward feedback over aesthetic polish or gameplay complexity.

# Research Context
- **Domain**: Feature-based reward learning, ecological validity in decision-making tasks
- **Participants**: Human subjects navigating the environment under time pressure
- **Independent variable**: The reward function (researcher-defined, maps tree attributes → reward)
- **Dependent variable**: Which trees participants choose to harvest, and in what order
- **Key constraint**: Tree attributes must be clearly visible; reward feedback must be unambiguous

# Gameplay
- Participant controls a single avatar in a 3D procedurally generated landscape
- A countdown timer limits each session
- Movement through the environment costs time
- Harvesting a tree costs time and yields a reward
- Goal: maximize total reward harvested before time runs out
- No combat, no inventory, no crafting — the core loop is navigate → observe → decide → harvest

# Tree System
Each tree has three continuous attributes, each randomly sampled per tree:
- **Shape** — e.g. canopy width, height, or trunk thickness (a visible morphological property)
- **Color** — a continuous value mapped to a visible hue or saturation gradient
- **Elevation** — the altitude at which the tree is placed in the terrain

A researcher-defined reward function `f(shape, color, elevation) → reward` is set before each session. This function can be linear, nonlinear, or involve interactions between attributes. Participants are never told the function — they must infer it from experience.

Every tree in the environment is unique due to continuous attribute sampling.

# Camera & Perspective
- Current plan: **fixed 45-degree top-down isometric** camera
- May be changed to: first-person, third-person follow, or rotation-on-turn
- Camera choice is a research variable — code should make it easy to swap perspectives
- Avoid camera motion that obscures tree attribute visibility

# Tech Stack
- Unity 6000.0 LTS (URP)
- C# 9.0
- Platform target: PC (Linux/Windows)
- Version control: Git/GitHub

# Project Structure
Assets/
  Scripts/
    Player/         — avatar controller, input, movement, harvesting action
    Trees/          — tree attribute generation, reward function, visual mapping
    World/          — procedural terrain and tree placement
    Session/        — session config (reward function, timer, parameters)
    Feedback/       — reward display, harvest feedback UI
    Data/           — data logging, session recording for research output
    Core/           — GameManager, ServiceLocator, singletons
    UI/             — HUD, timer display, session start/end screens
  Scenes/
    Main.unity      — primary game scene
  Prefabs/
    Player/
    Trees/          — tree prefabs with attribute-driven visuals
    World/
  ScriptableObjects/
    SessionConfig/  — reward function parameters, timing, tree density
    TreeConfig/     — attribute ranges, visual mapping curves

# Architecture Principles
- Singletons inherit from a generic Singleton<T> base class
- MonoBehaviours use [SerializeField] for all inspector-exposed fields
- Game events use C# Actions (not UnityEvents)
- ScriptableObjects used for session configuration and tree definitions
- Reward function is modular and swappable — defined in SessionConfig, not hardcoded
- Tree visuals are driven entirely by attribute values via AnimationCurves or gradient mappings
- No FindObjectOfType in production code — use ServiceLocator or direct references

# Data & Research Output
- All participant actions should be logged: position over time, trees harvested, rewards obtained, time remaining
- Log format should be CSV or JSON, written to a per-session file
- Session parameters (reward function, seed, timing) should be saved alongside behavioral data

# Git Workflow
- main: stable builds only
- dev: active development branch
- Feature branches: feature/description
- Always commit before starting a Claude session

# Current Focus
Project is empty — starting from scratch. Suggested build order:
1. Player movement (top-down avatar controller)
2. Basic procedural terrain
3. Tree generation with visible continuous attributes
4. Reward function framework and harvest mechanic
5. Timer and session management
6. Reward feedback UI
7. Data logging

# Do Not Modify
- ProjectSettings/ (unless explicitly asked)
- Packages/
- .meta files
- .git/
