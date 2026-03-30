# Foraging — Project Overview
A Unity-based 3D game built for psychology research on **feature-based reward learning** in naturalistic environments. Participants control an avatar navigating a virtual landscape, harvesting bushes to obtain rewards. The core research question is how participants learn an underlying reward function defined over continuous bush attributes.

This is a **research tool first, game second**. Design decisions prioritize ecological validity, perceptual clarity of bush attributes, and unambiguous reward feedback over aesthetic polish or gameplay complexity.

# Research Context
- **Domain**: Feature-based reward learning, ecological validity in decision-making tasks
- **Participants**: Human subjects navigating the environment under time pressure
- **Independent variable**: The reward function (researcher-defined, maps bush attributes → reward)
- **Dependent variable**: Which bushes participants choose to harvest, and in what order
- **Key constraint**: Bush attributes must be clearly visible and perceptually independent; reward feedback must be unambiguous
- **Prior management**: Attributes are chosen to minimize strong ecological priors — fruit count is held constant across all bushes to avoid count-based priors

# Gameplay
- Participant controls a single avatar in a 3D procedurally generated landscape
- A countdown timer limits each session
- Movement through the environment costs time
- Harvesting a bush costs time and yields a reward
- Goal: maximize total reward harvested before time runs out
- No combat, no inventory, no crafting — the core loop is navigate → observe → decide → harvest

# Bush Attribute System
Each bush has three continuous attributes, each randomly sampled per bush (normalized 0–1):

- **Shape** — canopy aspect ratio: squat/wide (0) to tall/narrow (1). Ecologically grounded in real shrub morphology. No strong reward prior.
- **Color** — hue of the fruit, mapped along an abstract blue→orange axis (avoids red/green ripeness priors). Clearly visible on fruits distributed across the dome surface.
- **Moisture** — soil moisture at the bush's location, sampled from a Perlin noise terrain map. Expressed visually as ground color (arid sandy → grassland green → swampy dark). Ecologically valid as a productivity cue. Varies continuously across the landscape.

A researcher-defined reward function `f(shape, color, moisture) → reward` is configured in SessionConfig before each session. The function supports nonlinear basis functions (Gaussian, sinusoidal, etc.) so reward does not need to be monotonically related to any attribute — intermediate values can yield higher rewards than extremes.

# Visual Design
- Bushes are procedurally generated hemisphere meshes (dome-up, flat base on ground)
- Canopy shape is controlled by scaling the hemisphere: wide/flat vs narrow/tall
- Fruits are runtime-generated spheres distributed across the dome surface using a Fibonacci/sunflower spiral pattern with per-bush seed jitter for even, non-clustered coverage
- Fruit count is constant across all bushes (configured in SessionConfig)
- Fruit color is the sole visual expression of the color attribute
- Ground is a flat plane textured with a Perlin noise moisture map using a 3-stop color gradient
- All visual parameters (colors, ranges, fruit count, fruit size, noise frequency) are tunable via SessionConfig in the Unity Inspector without touching code

# Camera
- Fixed 45° isometric follow camera — parented to the Player, follows movement without rotating
- Angle chosen to show both canopy shape (in profile) and fruit color (on dome surface) simultaneously

# Tech Stack
- Unity 6000.0 LTS (URP)
- C# 9.0
- New Unity Input System (PlayerInput component, Invoke Unity Events behavior)
- Platform target: PC (Linux/Windows)
- Version control: Git/GitHub

# Project Structure
Assets/
  Scripts/
    Player/
      PlayerController.cs     — WASD Rigidbody movement, trigger-based harvest detection
    Trees/
      TreeAttributes.cs        — struct: shape, color, moisture (all float 0-1)
      BasisFunctionType.cs     — enum: Linear, InvertedLinear, GaussianPeak, etc.
      RewardComponent.cs       — serializable: basis function + weight, Evaluate(float)
      RewardFunction.cs        — serializable: 3 RewardComponents, Evaluate(TreeAttributes)
      HemisphereMesh.cs        — static utility: generates cached hemisphere mesh
      Tree.cs                  — MonoBehaviour: applies attributes, generates fruits, trigger collider
    World/
      TerrainManager.cs        — generates Perlin noise moisture map, textures ground plane
      TreeGenerator.cs         — places bushes procedurally using seeded random placement
    Session/
      SessionConfig.cs         — ScriptableObject: all session parameters and visual ranges
  Scenes/
    SampleScene.unity          — main scene
  Prefabs/
    Trees/
      Tree.prefab              — canopy sphere only (no fruits, no trunk — all runtime generated)
  ScriptableObjects/
    SessionConfig/
      DefaultSession.asset     — default session configuration
  Materials/
    CanopyMaterial.mat         — double-sided URP/Lit material for bush canopy

# Architecture Principles
- **SessionConfig is the single source of truth** for all session parameters and visual ranges
- MonoBehaviours use [SerializeField] for all inspector-exposed fields
- Game events will use C# Actions (not UnityEvents)
- Reward function is modular and swappable — defined entirely in SessionConfig, never hardcoded
- Tree visuals are driven entirely by attribute values via SessionConfig ranges
- Procedural content uses WorldSeed for full reproducibility
- Fruits are runtime-instantiated (not prefab children) — no manual fruit management in Editor
- No FindObjectOfType in production code

# Key Design Decisions (and Rationale)
- **Fruit count constant**: avoids strong prior that more fruit = more reward
- **Abstract fruit color axis (blue→orange)**: avoids red/green ripeness associations
- **Moisture as terrain attribute**: ecologically valid (soil moisture predicts productivity), spatially continuous, no strong reward prior
- **Fibonacci spiral fruit placement**: ensures even dome coverage without clustering
- **Shape as aspect ratio not overall size**: decouples shape from size to avoid size-based priors
- **All visual ranges in SessionConfig**: allows rapid experimental iteration without code changes

# Session Configuration (DefaultSession)
All tunable from the Unity Inspector:
- Reward function (per-attribute basis functions and weights)
- Session duration, world seed, tree count
- Fruit count, fruit radius, fruit color range (low/high colors)
- Canopy width/height ranges, shape range
- Terrain colors (arid/grassland/swampy), noise frequency, noise octaves
- Player move speed, harvest duration

# Git Workflow
- main: stable builds only
- dev: active development branch
- Feature branches: feature/description
- Always commit before starting a Claude session

# Current State
Core visual environment is complete:
- ✅ Player movement (WASD, Rigidbody, top-down)
- ✅ Procedural bush generation with 3 continuous attributes
- ✅ Hemisphere mesh with Fibonacci fruit placement
- ✅ Perlin noise terrain with moisture-based ground coloring
- ✅ All visual parameters tunable via SessionConfig
- ✅ Reward function framework (modular basis functions)

# Next Steps (suggested build order)
1. Harvest mechanic — time cost, trigger detection, call SetHarvested()
2. Reward feedback UI — display reward value clearly on harvest
3. Session timer — countdown, session end screen
4. Data logging — record all actions to CSV/JSON per session
5. Session management — start screen, config selection, multiple runs

# Do Not Modify
- ProjectSettings/ (unless explicitly asked)
- Packages/
- .meta files
- .git/