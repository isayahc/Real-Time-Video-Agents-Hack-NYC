# RFD: Human Procedure to Machine Procedure Compiler

Status: Draft
Date: October 6, 2026
Project: Mapped Assembly / Forma
Target Event: Real-Time Video Agents Hack — NYC
Primary Benchmark: CREOLab
Related Datasets: FineBio, LSV / LabSuperVision, IBM Lab Actions, BioProBench

## 1. Summary

This RFD proposes a system that converts video demonstrations of human manual procedures into structured, machine-executable representations and then derives the physical capabilities required to automate those procedures.

The initial target domain is scientific laboratory work.

The system accepts video of a human performing a procedure and produces:
- Detected objects and object trajectories.
- Temporally segmented human actions.
- Physical state transitions.
- A structured, embodiment-independent Protocol IR.
- A set of required machine capabilities.
- A candidate automated machine architecture.
- A Forma-compatible specification suitable for generating a BOM, physical design, and rendered machine.

Core thesis:

Human demonstrations encode procedural knowledge, but the human embodiment should not be treated as part of the procedure itself.

Instead of copying human motion directly, the system identifies the underlying physical transformation being performed.

Example:

Human demonstration:
Hand + screwdriver + platinum wire

Observed transformation:
Straight wire → helical wire

Inferred physical requirements:
- constrain wire
- maintain tension
- maintain contact with cylindrical surface
- provide controlled rotation
- monitor resulting geometry

Machine realization:
Motorized mandrel + feeder + tensioner + camera

The resulting system acts as a compiler from human procedures to machine procedures.

## 2. Why This Matters

The primary economic problem is not simply that manual work exists.

The problem is that many economically important physical workflows depend on scarce skilled labor, tacit procedural knowledge, long training periods, repetitive manual operations, expensive employee turnover, difficult-to-fill technical positions, and bespoke automation engineering.

At the same time, much of the knowledge necessary to automate these workflows already exists in forms intended for humans:
- human demonstrations
- laboratory protocols
- SOPs
- instructional videos
- technician workflows
- existing production operations

The missing layer is a system capable of translating that knowledge into machine requirements.

Today, automation usually requires engineers to manually perform that translation:

Human process
→ Process study
→ Requirements engineering
→ Automation engineer
→ Mechanical design
→ Controls design
→ Integration
→ Automated cell

Protocol Compiler proposes:

Human process
→ Video + SOP
→ Protocol Compiler
→ Machine requirements
→ Forma / Mapped Assembly
→ Candidate automated cell

The economic opportunity is therefore not merely to replace labor with machines. It is to reduce the cost and engineering effort required to determine how a human process can be automated in the first place.

## 3. Labor Scarcity

Labor availability is already a constraint on physical industries.

Deloitte and the Manufacturing Institute estimate that U.S. manufacturing could require approximately 3.8 million new workers between 2024 and 2033, with as many as 1.9 million positions remaining unfilled if existing skills and applicant gaps persist.

The same basic pressure exists in laboratory work: staffing shortages, retirement, slow training pipelines, and difficulty recruiting qualified technical workers constrain capacity.

This creates a structural problem:

Demand for skilled physical work ↑
Available trained humans ↓

Increasing demand cannot always be addressed simply by hiring more people.

Sources:
https://www.deloitte.com/us/en/insights/topics/economy/spotlight/us-manufacturing-labor-impact.html
https://www.deloitte.com/us/en/about/press-room/deloitte-and-mi-study-shows-potential-for-ai-to-accelerate-manufacturing-skills-training.html
https://www.ascp.org/news/news-details//2025/10/15/ai--retirements--and-staffing-gaps--what-every-pathologist-and-medical-laboratory-professional-should-know-from-the-2024-vacancy-survey
https://www.ascp.org/news/news-details//2025/12/02/ai--staffing-pressures--and-a-shifting-workforce--inside-ascp-s-2024-vacancy-survey

## 4. Labor Is More Expensive Than Hourly Wages

The economic cost of a manual process is not simply hourly wage × hours worked.

It also includes:
- recruiting
- training
- supervision
- turnover
- overtime
- errors
- downtime
- knowledge loss
- capacity constraints

For manufacturing, Deloitte has cited survey results indicating that replacing one skilled frontline worker can cost tens of thousands of dollars.

Labor shortages therefore have secondary economic effects. A company may have demand for additional production but be unable to increase throughput because another trained technician cannot be recruited.

The constraint becomes:

Revenue opportunity
→ Available skilled labor
→ Maximum throughput

Automation can change the constraint.

## 5. The Automation Cost Problem

Traditional automation has its own economic limitation.

A task may technically be automatable but still not be economically worthwhile because deploying automation requires substantial non-recurring engineering.

For a new process, engineers may need to determine:
- what the operator actually does
- which steps are essential
- which tools are incidental
- what objects are manipulated
- what physical states change
- what tolerances matter
- what sensors are required
- what actuators are required
- what failure conditions exist
- how the resulting system should be arranged

Only after this analysis can conventional mechanical, electrical, controls, and robotics engineering begin.

Cost of automation =
hardware
+ software
+ integration
+ process engineering
+ custom mechanical design
+ controls engineering
+ validation

For low-volume or highly specialized processes, the engineering cost can dominate the hardware cost.

This helps explain why many manual workflows remain manual even when individual robotic components capable of performing the operations already exist.

## 6. Automating the Design of Automation

Protocol Compiler targets this upstream engineering bottleneck.

Instead of requiring an engineer to manually convert:

“This is how a person performs the procedure.”

into:

“The automated system requires these degrees of freedom, sensing modalities, manipulation capabilities, and process controls.”

the system attempts to infer that transformation automatically.

Human procedure
→ Observe
→ Understand physical transformation
→ Extract embodiment-independent protocol
→ Determine machine capabilities
→ Generate machine architecture

The economic product is therefore not only the automated machine. The product is also the reduction in engineering required to create that machine.

## 7. Automation Economics

A simplified automation decision can be expressed as:

Economic Value =
Labor capacity gained
+ Avoided hiring cost
+ Reduced training
+ Reduced turnover exposure
+ Increased throughput
+ Reduced repetitive work
+ Potential quality improvements
− Machine CAPEX
− Integration cost
− Maintenance
− Validation cost

Protocol Compiler primarily attacks:
- integration cost
- process engineering cost
- automation design cost

while making automation viable for smaller-volume processes.

Useful long-term metrics include:

Automation Engineering Cost Reduction =
(traditional engineering hours − compiler-assisted engineering hours)
÷ traditional engineering hours

Time to Automation =
time from human procedure recording to first viable machine specification

The objective is to reduce this from potentially weeks or months of engineering analysis toward hours or days for suitable processes.

## 8. Economic Expansion of the Automation Market

Conventional automation tends to favor:
- high volume
- stable processes
- high labor spend
- long production lifetimes

because the cost of automation engineering must be amortized across many units.

If machine design becomes substantially cheaper, automation becomes viable farther down the volume curve.

This can make automation practical for:
- laboratories
- pilot manufacturing
- small factories
- specialty manufacturing
- research facilities
- contract manufacturing
- agricultural operations
- low-volume assembly
- rapidly changing processes

The strategic opportunity is therefore larger than automating existing high-volume factories. It is enabling automation in environments that historically could not economically justify custom automation.

## 9. Preserving Scarce Human Expertise

The goal is not necessarily removing humans entirely.

Highly trained personnel often spend part of their time performing work that does not require the full breadth of their expertise.

For example:

Scientist — high-value work:
- experiment design
- interpretation
- troubleshooting
- hypothesis generation

Scientist — routine manual work:
- transferring material
- repetitive preparation
- loading equipment
- monitoring routine steps

Protocol Compiler can potentially separate these.

Human:
judgment, science, exception handling, process improvement

Machine:
repeatable physical execution, monitoring, material movement, routine manipulation

This changes the framing from replacing scientists to increasing the amount of science each scientist can perform.

## 10. Knowledge Capture

Labor shortages also create a knowledge-retention problem.

A skilled worker may possess years of procedural knowledge that is incompletely represented in formal documentation.

When the worker leaves:
employee leaves
→ tacit knowledge leaves
→ new employee is trained
→ process is slowly reconstructed

Video demonstrations create another form of institutional memory.

Protocol Compiler attempts to turn that memory into structured data:

Expert demonstration
→ Observation Graph
→ Protocol IR
→ Machine-capability model

This potentially makes procedural knowledge searchable, comparable, reusable, versionable, executable, and automatable.

VAST's role as persistent procedural memory becomes especially important here.

## 11. Why Scientific Protocols First

Scientific procedures are a useful starting domain because they often already possess:
- defined objectives
- expected outputs
- known tools
- repeated actions
- written protocols
- observable state changes
- quality requirements

They also frequently contain repetitive manipulation performed by expensive, highly trained personnel.

Scientific workflows therefore provide a useful test of both:
- Can the system understand the procedure?
- Can it derive an economically sensible automated embodiment?

The system can later generalize to other forms of physical work.

## 12. Goals

The system MUST:
## 1. Accept a video containing a human manual procedure.
## 2. Identify relevant physical objects.
## 3. Track those objects through time.
## 4. Divide the video into meaningful procedural steps.
## 5. Infer physical interactions between objects.
## 6. Infer relevant state transitions.
## 7. Distinguish task-relevant objects from irrelevant objects.
## 8. Produce a structured Protocol IR.
## 9. Remove unnecessary assumptions tied specifically to the human embodiment.
## 10. Convert protocol operations into machine capabilities.
## 11. Generate a candidate physical system satisfying those capabilities.
## 12. Preserve provenance from generated conclusions back to video evidence.
## 13. Evaluate procedure extraction against available ground truth.
## 14. Use the hackathon sponsor technologies as functional parts of the system.

## 13. Non-Goals

The initial implementation WILL NOT attempt to:
- autonomously execute wet-lab experiments
- control real laboratory hardware
- guarantee scientific correctness
- infer exact forces or material properties solely from video
- generate safety-critical laboratory automation
- perfectly reconstruct human biomechanics
- train a new foundation model
- solve arbitrary long-duration human tasks
- synthesize every possible machine embodiment
- automatically validate a generated machine physically

The hackathon prototype demonstrates the procedure-compilation pipeline, not autonomous laboratory deployment.

## 14. Initial Benchmark

The initial system SHOULD use CREOLab.

CREOLab is useful because it provides:
- laboratory procedure video
- step-level ground truth
- object annotations
- object locations
- unusual use of common tools
- irrelevant or distracting objects

The last two properties are particularly valuable.

The system should not infer:

screwdriver detected
→ screw-driving operation

Instead, it should use temporal evidence:

wire contacts screwdriver shaft
screwdriver rotates
contact persists
wire changes geometry
→ wire forming operation

This tests whether the system understands observed physical transformations rather than relying on object priors.

Dataset:
https://github.com/ToyotaCRDL/CREOLab

## 15. Example Benchmark Task

The initial demonstration SHOULD use the CREOLab example involving platinum wire being formed around a screwdriver.

Human implementation:
hand + platinum wire + screwdriver

Observed procedure:
## 1. constrain wire
## 2. establish contact between wire and cylindrical shaft
## 3. rotate shaft relative to wire
## 4. maintain tension
## 5. continue until desired coil geometry is achieved

State transition:
wire.geometry: straight → helical

The screwdriver itself is not required.

The actual capabilities are:
- rotational actuation
- controlled wire feeding
- wire tensioning
- cylindrical forming surface
- visual inspection

Candidate automated embodiment:
Motor
→ Rotating mandrel
← Wire tensioner
← Wire feeder
Camera → monitors turns / geometry

This example makes the central thesis visually obvious: the system learned the operation rather than copying the human.

## 16. System Architecture

Human Procedure Video
        ↓
VAST AI OS
video + metadata + procedural memory
        ↓
┌───────────────────────┬────────────────────────┐
│                       │                        │
YOLO                    NVIDIA Cosmos            Semantic retrieval
detection/tracking      physical reasoning       prior procedure lookup
│                       │                        │
└───────────────────────┴────────────────────────┘
        ↓
Observation Graph
        ↓
Protocol IR
        ↓
Automation Compiler (Grok / sponsor LLM)
        ↓
Machine Capability Specification
        ↓
Mapped Assembly / Forma
        ↓
Machine design / BOM / render

Model inference runs on CoreWeave infrastructure.

W&B Weave records and evaluates model calls throughout the pipeline.

## 17. Sponsor Technology Integration

Sponsor technology SHOULD be functionally necessary rather than included only for presentation purposes.

### 17.1 VAST Data

VAST acts as the system's persistent procedural memory.

It stores and indexes:
Video
- segments
- detected objects
- object tracks
- Cosmos observations
- inferred interactions
- state changes
- Protocol IR
- machine capabilities
- evaluation results

The system SHOULD support queries such as:
“Find all segments where an object rotates while maintaining physical contact with another object.”

and:
“Find prior procedures involving a straight-to-helical geometry transformation.”

VAST therefore acts as searchable memory of physical procedures rather than passive video storage.

### 17.2 NVIDIA Cosmos

Cosmos provides temporal and physical interpretation of the video.

The input SHOULD be divided into overlapping temporal windows, for example:
00:00–00:06
00:05–00:11
00:10–00:16

Cosmos SHOULD produce constrained structured observations containing:
- actor
- action
- manipulated object
- affected object
- contact state
- start/end timestamps
- inferred state change
- confidence

The primary Cosmos responsibility is not caption generation. It is to answer:

WHAT CHANGED?

### 17.3 YOLO

YOLO provides fast object detection and temporal tracking.

Each detection should include:
- frame/timestamp
- track ID
- class
- bounding box
- confidence

Object tracks provide grounding for Cosmos observations and enable relationships such as:
- object A approaches object B
- object A contacts object B
- object A and B move together
- object A separates from B

Detection and tracking SHOULD remain distinct from semantic procedure interpretation.

### 17.4 CoreWeave

CoreWeave SHOULD provide GPU infrastructure for:
- Cosmos inference
- YOLO inference
- other event-provided models

The application SHOULD treat inference infrastructure as independent from procedure logic so the architecture remains portable after the hackathon.

### 17.5 Weights & Biases / Weave

W&B Weave SHOULD trace all meaningful reasoning stages:

process_video
- segment_video
- detect_objects
- track_objects
- cosmos_observation
- merge_observations
- infer_state_changes
- build_protocol_ir
- compile_capabilities
- generate_machine_spec

Each run SHOULD retain:
- model
- prompt
- latency
- input
- output
- errors
- confidence
- evaluation result

### 17.6 SpaceXAI / Grok

Grok or another sponsor-provided reasoning model SHOULD own the automation-compiler layer: converting an embodiment-independent Protocol IR into physical machine-capability requirements.

The LLM should reason symbolically about engineering requirements, not perform primary video perception.

### 17.7 Cursor

Cursor is the development environment and implementation accelerator for the hackathon build.

### 17.8 Mapped Assembly / Forma

Mapped Assembly / Forma performs physical machine synthesis from the derived capability specification.

## 18. Observation Graph

The perception layers SHOULD produce an intermediate Observation Graph before generating the Protocol IR.

Example:

OBJECT wire_01
OBJECT tool_02

EVENT e1
type: grasp
actor: human
object: wire_01

EVENT e2
type: contact
object_a: wire_01
object_b: tool_02

EVENT e3
type: rotate
object: tool_02
axis: estimated_z

EVENT e4
type: geometry_change
object: wire_01
before: straight
after: helical

Each event SHOULD retain:
- timestamps
- contributing video frames
- model confidence
- detected objects
- source model
- optional ground-truth match

The Observation Graph prevents Protocol IR generation directly from unconstrained freeform captions.

## 19. Protocol IR

Protocol IR represents the procedure independently from any particular machine embodiment.

Conceptual example:

protocol:
  id: wire_coil_001
  name: form_wire_coil

objects:
  wire:
    type: flexible_filament
  mandrel:
    type: cylindrical_surface

initial_state:
  wire:
    geometry: straight
    constrained: false

desired_state:
  wire:
    geometry: helical

operations:
  - id: constrain_wire
    action: constrain
    object: wire
    postcondition: wire.constrained = true

  - id: establish_contact
    action: contact
    object_a: wire
    object_b: mandrel

  - id: wind_wire
    action: relative_rotation
    moving_object: mandrel
    affected_object: wire
    constraints:
      contact: maintained
      wire_tension: maintained
    postcondition:
      wire.geometry: helical

## 20. Protocol IR Design Principles

The IR MUST distinguish between:

Intent:
Form wire into a helical geometry.

Physical operation:
Rotate a cylindrical surface relative to a tensioned wire.

Human implementation:
Person rotates screwdriver with their hand.

Machine implementation:
Motor rotates mandrel while a tensioner controls the wire.

Only the first two belong in the core Protocol IR.

Human and machine embodiments are implementations.

## 21. Automation Compiler

The Automation Compiler converts Protocol IR operations into machine-level capability requirements.

Input:
relative rotation
+ contact maintained
+ wire tension maintained
+ postcondition wire.geometry = helical

Output:
- workholding / constrain wire
- force or tension control
- rotary actuation
- material feeding
- machine vision
- stop condition based on target turn count or target geometry

The compiler SHOULD avoid prematurely selecting specific hardware.

Bad:
Use a NEMA17 motor.

Good:
Controlled rotary actuation is required.

Hardware selection occurs later.

## 22. Machine Capability Specification

The compiler output becomes a Forma-compatible specification.

Conceptual example:

machine objective:
transform wire from straight geometry to helical geometry

required capabilities:
- rotary actuation
- material feeding
- tension control
- workholding
- visual monitoring

required sensing:
- camera

feedback targets:
- turn count
- coil spacing
- wire position

The specification should also surface unresolved requirements such as:
- required wire tension
- required rotational torque
- acceptable coil-spacing error

Unknowns MUST NOT be silently invented.

## 23. Forma / Mapped Assembly

Forma receives the capability specification and generates a candidate machine.

Outputs MAY include:
- system hierarchy
- hardware architecture
- components
- BOM
- wiring
- STEP geometry
- rendered machine
- machine states
- candidate controller architecture

Possible generated architecture:

Machine
- Frame
- Wire spool
- Wire feeder
- Tension mechanism
- Rotary actuator
  - Mandrel
- Camera
- Controller

The initial hackathon implementation does not need to validate the machine physically.

It must demonstrate that machine architecture is derived from the inferred procedure rather than hard-coded.

## 24. Evaluation

The system must be evaluated at multiple abstraction levels.

Object detection:
- precision
- recall
- mAP
- tracking consistency

Procedure extraction:
- step recall
- step precision
- step ordering accuracy
- temporal overlap

State transition accuracy:
- correctness of before/after state
- relevance of the transition to the procedure

A prediction can be physically true but procedurally irrelevant. The system therefore requires relevance scoring in addition to raw observation accuracy.

## 25. Distractor Robustness

CREOLab's irrelevant objects enable an important benchmark.

The experiment SHOULD measure protocol accuracy as distractor count increases.

Compare at least two approaches:

Baseline:
single VLM prompt → procedure

System:
object tracking
+ temporal reasoning
+ state transitions
+ Protocol IR

This produces a quantifiable reason for the architecture rather than simply a more complicated pipeline.

## 26. Automation Evaluation

The generated machine specification cannot be fully physically validated during the hackathon.

However, it can be evaluated structurally.

Primitive Coverage =
required physical operations represented
÷ total required physical operations

Example:

Operation requires:
- contact
- tension
- rotation

Generated machine supports:
- contact ✓
- tension ✓
- rotation ✓

Primitive coverage = 100%

The compiler SHOULD explicitly identify unresolved physical requirements rather than invent values.

## 27. Provenance

Every derived operation SHOULD be traceable to source video evidence.

Example:

operation: wind_wire

evidence:
- video_id: creolab_0042
- start: 8.4
- end: 14.1
- object_tracks:
  - wire_01
  - screwdriver_02
- observations:
  - contact
  - rotation
  - geometry_change

This creates:

machine requirement
→ protocol operation
→ physical observation
→ video frames

This provenance is valuable for debugging, evaluation, and scientific trust.

## 28. API Boundaries

The system SHOULD use explicit interfaces between stages.

Core types:
- ObservationEvent
- StateChange
- ProtocolOperation
- ProtocolIR
- MachineCapability
- MachineCapabilitySpecification
- HardwareIntermediateRepresentationRequest

No model should directly mutate downstream artifacts outside its defined interface.

The implementation SHOULD use strict typed schemas, preferably Pydantic models.

## 29. User Interface

The demo UI SHOULD emphasize transformation between abstraction levels.

Panel 1 — Original video
- video playback
- object overlays
- timeline

Panel 2 — Observed events
- grasp
- contact
- rotate
- geometry change

Panel 3 — Protocol
- constrain wire
- contact mandrel
- rotate
- maintain tension

Panel 4 — Machine capabilities
- workholding
- rotary actuation
- tension control
- machine vision

Panel 5 — Generated machine
- Forma render
- BOM
- system hierarchy

Users SHOULD be able to click a machine requirement and inspect the video evidence from which it was derived.

## 30. Friday MVP

The Friday MVP SHALL support one procedure end-to-end.

Input:
One CREOLab video.

Output:
## 1. Video playback.
## 2. Detected/tracked objects.
## 3. Extracted procedural steps.
## 4. At least one explicit physical state transition.
## 5. Protocol IR.
## 6. Machine capability specification.
## 7. Forma-generated machine architecture.
## 8. Render or system hierarchy.
## 9. W&B trace.
## 10. Provenance linking generated machine requirements back to video timestamps.

## 31. Stretch Goals

If the MVP is completed:

Multiple procedures:
Run several CREOLab examples.

Procedure similarity search:
Use VAST to find procedures containing equivalent physical transformations.

Cross-embodiment equivalence:
Show two different human demonstrations producing the same Protocol IR.

Error detection:
Compare observed procedure against expected protocol and identify missing, reordered, or extraneous steps.

Existing-machine matching:
Ask whether an existing machine already has the capabilities required to execute the protocol.

Closed-loop improvement:
human demo
→ machine design
→ machine run
→ failure video
→ updated protocol or machine

## 32. Future Direction

The architecture should generalize beyond scientific protocols.

Potential domains include:
- laboratory work
- manufacturing
- assembly
- repair
- maintenance
- food preparation
- agriculture
- construction
- inspection
- material handling

The generalized system becomes a Human Procedure Compiler rather than specifically a Lab Automation System.

The scientific-protocol domain is the initial benchmark because procedures are naturally structured and often have known expected outcomes.

## 33. Longer-Term Research Question

Can machines acquire executable procedural knowledge from human demonstrations without inheriting unnecessary assumptions about human embodiment?

A successful system should understand that:

human hand
may mean
grasp capability

and:

human rotates screwdriver
may mean
controlled relative rotation around an axis

The goal is therefore not imitation.

The goal is abstraction.

## 34. Risks

Hallucinated physical causality:
A VLM may confuse correlation with causation.

Mitigation:
- require temporal evidence
- use object tracking
- maintain confidence
- preserve provenance
- distinguish observations from inferences

Missing physical parameters:
Video may reveal an action but not force, torque, temperature, pressure, material composition, or tolerance.

The system MUST surface these as unknowns.

Overfitting to human tools:
The model may infer “screwdriver required” instead of “cylindrical rotating mandrel required.”

The automation compiler must explicitly remove embodiment-specific details.

Unsafe protocol interpretation:
Generated machine procedures MUST NOT be assumed safe for actual laboratory execution without validation.

Evaluation ambiguity:
Several machine designs may correctly realize the same protocol.

Machine-generation evaluation therefore focuses initially on capability coverage rather than a single “correct” design.

## 35. Success Criteria

The hackathon prototype is successful if, for at least one unseen procedure video, it demonstrates:

video
→ objects
→ actions
→ state transitions
→ Protocol IR
→ machine capabilities
→ generated machine

while satisfying:
- outputs are structured rather than only freeform prose
- machine capabilities are not manually hard-coded
- machine requirements are traceable to source video
- irrelevant objects do not automatically become machine requirements
- sponsor technologies perform meaningful architectural roles
- Forma generates a physical architecture from inferred requirements

## 36. Sponsor Mapping

VAST AI OS:
Persistent video, metadata, embeddings, procedural memory, semantic retrieval.

NVIDIA Cosmos:
Temporal physical reasoning and interaction/state interpretation.

YOLO:
Object detection and tracking.

CoreWeave:
GPU inference infrastructure.

Weights & Biases / Weave:
Tracing, evaluation, observability.

SpaceXAI / Grok:
Protocol-to-machine-capability compilation and engineering reasoning.

Cursor:
Development environment.

Mapped Assembly / Forma:
Physical machine synthesis.

## 37. Demo Narrative

## 1. Play a human laboratory procedure.
## 2. Show object tracks over the video.
## 3. Show extracted observations appearing over time.
## 4. Highlight the relevant physical state transition.
## 5. Generate the Protocol IR.
## 6. Remove human-specific implementation details.
## 7. Generate machine capabilities.
## 8. Ask Forma to create a machine satisfying them.
## 9. Display the machine architecture/render.
## 10. Click a machine capability and jump to the frames that caused the system to infer it.

Critical reveal:

The human used a screwdriver. The machine does not.

The system recognized that the actual requirement was controlled relative rotation around a cylindrical surface while maintaining wire tension.

That demonstrates procedure understanding rather than action imitation.

## 38. Economic Thesis

There is more physical work to perform than there are skilled humans available to perform it.

↓
Automation can fill part of this gap.

↓
But custom automation itself requires scarce engineering labor and is too expensive for many workflows.

↓
Existing human demonstrations already encode much of the information needed to describe those workflows.

↓
Protocol Compiler converts those demonstrations into machine requirements.

↓
Mapped Assembly converts the requirements into candidate machines.

↓
The cost and time required to automate a new physical process falls.

The ultimate objective is not simply to build robots that replace labor.

It is to make the long tail of physical work economically automatable.

## 39. One-Sentence Definition

Protocol Compiler converts videos of humans performing physical procedures into embodiment-independent protocols and machine specifications that can be used to design automated systems.

## 40. Working Pitch

Skilled labor shortages are increasingly constraining laboratories and physical industries, but automating a new workflow is itself expensive because engineers must first translate human procedures into machine requirements. Protocol Compiler automates that translation. It watches a person perform a physical task, reconstructs the underlying state transitions, removes assumptions tied to the human body, and compiles the procedure into the capabilities an automated machine actually needs. Mapped Assembly can then generate a candidate physical system capable of performing it.

Short pitch:

We automate the design of automation. Give us a video of a person performing a physical procedure, and we turn it into a machine specification.

Economic pitch:

There are not enough skilled workers to scale every physical industry by hiring alone, while conventional automation remains too expensive to engineer for the long tail of specialized tasks. We use video AI to extract how work is performed and compile it directly into machine requirements, reducing the engineering cost required to automate new processes.
