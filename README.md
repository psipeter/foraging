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

# Workflow
This chat (Claude) is used for high-level discussion, debugging diagnosis, and generating Cursor prompts.
**Claude should never output direct code edits. Instead, Claude outputs a Cursor prompt that instructs Cursor to make the change.**
Cursor handles all actual file edits via the prompt provided by Claude.

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
- Ground is a mesh with Perlin noise elevation and vertex color moisture gradient
- Dynamic day/night cycle: sun arc drives directional light rotation, color, and intensity; ambient light tints terrain and canopy over session duration
- Tree highlight: pulsing semi-transparent disc projected onto terrain surface when player is in harvest range
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
      PlayerController.cs       — non-kinematic physics movement, terrain-following, trigger-based harvest detection
    Trees/
      TreeAttributes.cs          — struct: shape, color, moisture (all float 0-1)
      BasisFunctionType.cs       — enum: Linear, InvertedLinear, GaussianPeak, InvertedGaussian, Constant
      RewardComponent.cs         — serializable: basis function + weight, Evaluate(float)
      RewardFunction.cs          — serializable: 3 RewardComponents, Evaluate(TreeAttributes)
      HemisphereMesh.cs          — static utility: generates cached hemisphere mesh
      Tree.cs                    — MonoBehaviour: applies attributes, generates fruits, colliders, lighting, highlight
      FruitMaterialManager.cs    — static: caches unlit fruit materials by color
      TreeHighlight.cs           — terrain-projected pulsing disc highlight
    World/
      TerrainManager.cs          — generates Perlin noise elevation mesh, vertex color moisture map, runtime lighting tint
      TreeGenerator.cs           — places bushes procedurally using seeded random placement
    Session/
      SessionConfig.cs           — ScriptableObject: ALL session and visual parameters
      SunController.cs           — drives directional light arc, sky color, ambient tinting over session duration
      HarvestManager.cs          — manages harvest process, per-fruit reward sampling, events
      GameManager.cs             — distributes SessionConfig to all systems at startup
    UI/
      HarvestUI.cs               — floating reward text, score HUD
      SessionTimerUI.cs          — countdown timer, session end panel
    Data/
      DataLogger.cs              — movement CSV, harvest CSV, session metadata JSON
  Scenes/
    SampleScene.unity            — main scene
  Prefabs/
    Trees/
      Tree.prefab                — canopy sphere only (no fruits, no trunk — all runtime generated)
    UI/
      FloatingText.prefab        — floating reward number UI element
  ScriptableObjects/
    SessionConfig/
      DefaultSession.asset       — default session configuration
      Config_1_Linear.asset      — one feature, linear
      Config_2_Gaussian.asset    — one feature, gaussian peak
      Config_3_ThreeLinear.asset — three features, all linear
      Config_4_Mixed.asset       — three features, mixed linear/nonlinear
      Config_5_AllNonlinear.asset— three features, all nonlinear
  Materials/
    CanopyMaterial.mat           — double-sided URP/Lit material for bush canopy
    TerrainMaterial.mat          — uses custom VertexColor shader with shadow receiving
  Shaders/
    VertexColor.shader           — URP unlit + shadow receiving shader for terrain
    FruitUnlit.shader            — fully unlit shader for fruits (_Color property)
    RingUnlit.shader             — transparent unlit shader for tree highlight disc

# Architecture Principles
- **GameManager is the single point of SessionConfig assignment** — never assign SessionConfig directly in Inspector on individual components; GameManager distributes it in Awake()
- **SessionConfig is the single source of truth** for ALL session parameters and visual ranges
- Components that receive SessionConfig from GameManager use `public SessionConfig sessionConfig` (no [SerializeField])
- Components that need Inspector wiring use `[SerializeField] private` fields
- `[SerializeField] public` is never correct — avoid it
- MonoBehaviours use [SerializeField] private for all inspector-exposed fields
- Game events use C# Actions (not UnityEvents)
- Reward function is modular and swappable — defined entirely in SessionConfig, never hardcoded
- Tree visuals driven entirely by attribute values via SessionConfig ranges
- Procedural content uses WorldSeed for full reproducibility
- Fruits are runtime-instantiated (not prefab children) — no manual fruit management in Editor
- No FindObjectOfType in production code (FindObjectsByType acceptable for infrequent calls)
- Player uses non-kinematic Rigidbody with zero-friction physics material
- Player/Terrain/Tree on separate layers — collision matrix prevents terrain sliding while allowing tree collision
- Terrain following via downward raycast each FixedUpdate, not physics gravity

# Layer Setup
- **Default**: ground plane (Terrain), general scene objects
- **Terrain**: Ground GameObject — Player does not physically collide with this layer
- **Tree**: all Tree GameObjects and children — Player physically collides with this layer
- **Player**: Player GameObject only
- Layer Collision Matrix: Player↔Terrain unchecked, Player↔Tree checked

# Reward System
- Bush reward = weighted sum of basis functions, no normalization: `R = w1*f1(shape) + w2*f2(color) + w3*f3(moisture)`
- Per-fruit reward = `round(Gaussian(bushReward, rewardStd))`, clamped to >= 0
- Each fruit independently samples from the bush reward distribution
- Total harvest reward = sum of all per-fruit rewards
- Running total tracked across session
- Reward function configured entirely in SessionConfig per experiment

# Session Configuration (SessionConfig)
All tunable from the Unity Inspector on the active config asset:
- Reward function (per-attribute basis functions, weights, peaks, widths)
- Session duration, world seed, tree count
- Fruit count, fruit radius, fruit color range (low/high)
- Canopy width/height ranges, shape range
- Terrain colors (arid/grassland/swampy), noise frequency, noise octaves, max elevation, mesh resolution
- World half extent, color contrast
- Sun arc height, sun colors (dawn/noon), sky colors (dawn/noon/dusk), ambient colors
- Player move speed, fruit harvest duration, reward std

# Data Logging
Three files per session saved to `ForagingData/` in project root (gitignored):
- `movement.csv` — sampled every 0.1s: position, heading, camera transform, visible tree IDs and distances
- `harvests.csv` — per harvest: tree ID, position, attributes, true reward, per-fruit rewards, running total
- `session_metadata.json` — session config, reward function, camera parameters, full tree registry

# Known Limitations
- Terrain does not self-shadow (URP limitation at landscape scale)
- Shadow bias artifacts at very low sun angles — mitigated by minSunElevation on SunController
- Player capsule visually overlaps wide bushes slightly — will improve with proper player model
- FruitMaterialManager cache persists across Play mode sessions in Editor
- ForagingData/ folder is gitignored — back up participant data separately before pushing
- Custom shaders must be explicitly added to Always Included Shaders in Project Settings → Graphics, 
  or Shader.Find() will return null in standalone builds

# Git Workflow
- main: stable builds only
- dev: active development branch
- Feature branches: feature/description
- Always commit before starting a Claude session

# Current State
Core systems complete and stable: player movement, terrain, procedural bushes, 
day/night cycle, harvest mechanic, reward system, data logging, session management, UI.

## Recently completed
- Border objects (BorderObject.cs, BorderGenerator.cs) — perimeter enclosure
- Floating reward numbers rise from individual fruit positions
- Canopy size and highlight radius fixes

# Conversation Handoff
When starting a new Claude chat, paste: README.md, .cursorrules, and the 2-3 C# files most relevant to the current task.

## Recent Decisions (update as project evolves)
- Fruits use unlit shader — do not switch to lit materials
- Canopy uses double-sided URP/Lit — do not change to single-sided
- Player is non-kinematic Rigidbody
- FruitMaterialManager cache is intentionally persistent across Play sessions
- Reward function deliberately has no normalization — this is a research decision, not an oversight

## Active Debugging / In-Progress Work
- Current issue: none
- Recently completed: session flow overhaul — instructions from StreamingAssets/instructions.txt, between-session panel, score screen with Space to continue
- Next: font polish, sound, or participant ID screen

# Do Not Modify
- ProjectSettings/ (unless explicitly asked)
- Packages/
- .meta files
- .git/
- ForagingData/ (participant data)