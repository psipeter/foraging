# Foraging — Project Overview
A Unity-based 3D game built for psychology research on **feature-based reward learning** in naturalistic environments. Participants control an avatar navigating a virtual landscape, harvesting bushes to obtain rewards. The core research question is how participants learn an underlying reward function defined over continuous bush attributes.

This is a **research tool first, game second**. Design decisions prioritize ecological validity, perceptual clarity of bush attributes, and unambiguous reward feedback over aesthetic polish or gameplay complexity.

# Research Context
- **Domain**: Feature-based reward learning, ecological validity in decision-making tasks
- **Participants**: Human subjects navigating the environment under time pressure
- **Independent variable**: The reward function (researcher-defined, maps bush attributes → reward)
- **Dependent variable**: Which bushes participants choose to harvest, and in what order
- **Key constraint**: Bush attributes must be clearly visible and perceptually independent; reward feedback must be unambiguous
- **Prior management**: Attributes chosen to minimize strong ecological priors — fruit count is held constant across all bushes to avoid count-based priors; fruit color uses an abstract blue→orange axis to avoid red/green ripeness associations

# Gameplay
- Participant controls a single avatar in a 3D procedurally generated landscape
- A countdown timer limits each session (sunrise → sunset)
- Movement through the environment costs time
- Harvesting a bush costs time and yields a reward
- Goal: maximize total reward harvested before time runs out
- No combat, no inventory, no crafting — core loop is navigate → observe → decide → harvest

# Attribute-to-Visual Mapping
Each bush has three continuous attributes (normalized 0–1), each with a distinct visual channel:

| Attribute | Visual Channel | Ecological Level | Prior Strength |
|---|---|---|---|
| **Shape** | Canopy aspect ratio (squat/wide → tall/narrow) | Tree | Weak |
| **Color** | Fruit hue (blue → orange, abstract axis) | Fruit | Weak |
| **Moisture** | Ground color + terrain elevation | Environment | Weak-moderate |

Fruits are **unlit** — their color is always fully readable regardless of lighting conditions. Canopy and terrain respond to ambient lighting for time-of-day realism.

# Visual Design
- Bushes are procedurally generated hemisphere meshes (dome-up, flat base on ground)
- Canopy shape controlled by scaling the hemisphere: wide/flat vs narrow/tall
- Fruits are runtime-generated spheres distributed across the dome surface using a Fibonacci/sunflower spiral pattern with per-bush seed jitter for even coverage
- Fruit count is constant across all bushes (configured in SessionConfig)
- Ground is a flat-based mesh with Perlin noise elevation and vertex color moisture gradient
- Dynamic day/night cycle: sun arc drives directional light rotation, color, and intensity; ambient light tints terrain and canopy over session duration
- All visual parameters tunable via SessionConfig in the Unity Inspector

# Camera
- Fixed 45° isometric follow camera — parented to Player, follows movement without rotating
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
      PlayerController.cs       — WASD kinematic movement, terrain-following, trigger-based harvest detection
    Trees/
      TreeAttributes.cs          — struct: shape, color, moisture (all float 0-1)
      BasisFunctionType.cs       — enum: Linear, InvertedLinear, GaussianPeak, etc.
      RewardComponent.cs         — serializable: basis function + weight, Evaluate(float)
      RewardFunction.cs          — serializable: 3 RewardComponents, Evaluate(TreeAttributes)
      HemisphereMesh.cs          — static utility: generates cached hemisphere mesh
      Tree.cs                    — MonoBehaviour: applies attributes, generates fruits, trigger collider, lighting update
      FruitMaterialManager.cs    — static: caches unlit fruit materials by color
    World/
      TerrainManager.cs          — generates Perlin noise elevation mesh, vertex color moisture map, runtime lighting tint
      TreeGenerator.cs           — places bushes procedurally using seeded random placement
    Session/
      SessionConfig.cs           — ScriptableObject: ALL session and visual parameters
      SunController.cs           — drives directional light arc, sky color, ambient tinting over session duration
  Scenes/
    SampleScene.unity            — main scene
  Prefabs/
    Trees/
      Tree.prefab                — canopy sphere only (no fruits, no trunk — all runtime generated)
  ScriptableObjects/
    SessionConfig/
      DefaultSession.asset       — default session configuration
  Materials/
    CanopyMaterial.mat           — double-sided URP/Lit material for bush canopy
    TerrainMaterial.mat          — uses custom VertexColor shader with shadow receiving
  Shaders/
    VertexColor.shader           — URP unlit + shadow receiving shader for terrain
    FruitUnlit.shader            — fully unlit shader for fruits (_Color property)

# Architecture Principles
- **SessionConfig is the single source of truth** for ALL session parameters and visual ranges — never hardcode values that researchers might want to change
- MonoBehaviours use [SerializeField] for all inspector-exposed fields
- Game events will use C# Actions (not UnityEvents)
- Reward function is modular and swappable — defined entirely in SessionConfig, never hardcoded
- Tree visuals driven entirely by attribute values via SessionConfig ranges
- Procedural content uses WorldSeed for full reproducibility
- Fruits are runtime-instantiated (not prefab children) — no manual fruit management in Editor
- No FindObjectOfType in production code (FindObjectsByType is acceptable for infrequent calls)
- Terrain and canopy lighting tinted at runtime by SunController via ambient color multiplication

# Key Design Decisions (and Rationale)
- **Fruit count constant**: avoids strong prior that more fruit = more reward
- **Abstract fruit color axis (blue→orange)**: avoids red/green ripeness associations
- **Moisture as terrain attribute**: ecologically valid, spatially continuous, no strong reward prior
- **Unlit fruit materials**: fruit color always readable regardless of time of day
- **Fibonacci spiral fruit placement**: ensures even dome coverage without clustering
- **Shape as aspect ratio not overall size**: decouples shape from size to avoid size-based priors
- **All visual ranges in SessionConfig**: allows rapid experimental iteration without code changes
- **Kinematic Rigidbody**: player position driven entirely by code, no physics interference

# Session Configuration (DefaultSession)
All tunable from the Unity Inspector:
- Reward function (per-attribute basis functions and weights)
- Session duration, world seed, tree count
- Fruit count, fruit radius, fruit color range, sun intensities
- Canopy width/height ranges, shape range
- Terrain colors (arid/grassland/swampy), noise frequency, noise octaves, max elevation, mesh resolution
- World half extent, color contrast
- Sun arc height, rise direction, sun colors (dawn/noon), sky colors (dawn/noon/dusk), ambient colors
- Player move speed, harvest duration

# Known Limitations
- Terrain does not self-shadow (URP limitation at landscape scale) — hills do not cast shadows onto adjacent hills
- Shadow bias artifacts at very low sun angles — mitigated by minSunElevation on SunController
- FruitMaterialManager cache persists across Play mode sessions in Editor — restart Unity if fruit colors appear stale

# Git Workflow
- main: stable builds only
- dev: active development branch
- Feature branches: feature/description
- Always commit before starting a Claude session

# Current State
- ✅ Harvest mechanic: Space to harvest, player frozen during harvest
- ✅ Sequential fruit collection with per-fruit reward feedback
- ✅ Gaussian noise on per-fruit rewards for distributional experience
- ✅ Floating reward numbers with rise/linger/fade animation
- ✅ Summary total shown on harvest completion
- ✅ Running score displayed in HUD

# Next Steps (suggested build order)
1. Harvest mechanic — time cost, trigger detection, call SetHarvested()
2. Reward feedback UI — display reward value on harvest
3. Session timer — countdown display, session end screen
4. Data logging — record all actions to CSV/JSON per session
5. Session management — start screen, config selection, multiple runs

# Do Not Modify
- ProjectSettings/ (unless explicitly asked)
- Packages/
- .meta files
- .git/