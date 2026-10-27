# P9 机器人自身状态 独立审查

No blocking issue found for exact frozen P9 CPU/fake candidate. New derived robot-self observation domain must be explicitly versioned; no genuine P9 model/task success established.

独立聚焦 CPU：**130 passed / 0 failed / 0 skipped**。另解析作者 full CPU760/13skip、Git-free82通过；未重复执行这两套。

- **information boundary**：pass。Production FK function accepts only q7, actualpublicTCP, publicepisode/observation/time and hash-locked staticnumericmodel. No task/environment/object/seat/obstacle query, simulator link pose, teacher phase, collision, clearance, support or planner. Fake poisoned object/teacher/scorer inputs excluded. Newly sent data is nominal own-state derivation, not native link-state readback.
- **FK and TCP convention**：pass。URDFjoint order1..7(rad), base_link/world transform inferred as T_world_TCP*inverse(T_base_TCP(q)); selected link poses compose same base with FK. Three nontrivial independentMDH cases and noncommuting worldorientation compare successfully. T_hand_TCP z=.1m/Rz(pi),wxyz[0,0,0,1] is explicitly checked. AnchoredTCPagreement is construction, not independent realcalibration.
- **model provenance and portable runtime**：pass。Numericmodel bytes8fa2321d and canonicalcontent81275b52 locked; URDFsourcee9024642 and sourceboxes5f3ff56c registered; regeneration fixture byte-identical. Runtime needs normalGit JSON+numpy, noURDF/USD/LFS/Git parsing or sourceauthorpaths. Tamperedmodel/nonfinite/invalidshape/quaternion/jointlimit inputs failclosed. Numericmodel is code-release artifact, not a silent HF assetrevision change.
- **three local robot boxes**：independently_recomputed_CPU。Read-only lockedFrankUSD312a326e body-local authored input vertices give exact extrema matching link6(11639),link7(6183),hand(3319) modelboxes. No arbitrary padding/obstaclelocation. Box is conservative for inputvertices/hulls but can fillconcavities, excludesfingers/heldvessel/cooking/contactoffset/sweep. Existing3publicqsample USDjoint-vsURDF frameproof supports nominalattachment only; no global collision precision claim.
- **P4 P6 P7 P8 preservation**：pass。Only3line explicit robot_self_state dispatch precedes unchangedP8/P7routes. P7/P8modules/profiles plus client/physicalcamera/scene/control/scorer/core all17protected files equal4226419. Focusedtests compare old public/direct fakewire and frozenP4/P6, retainoriginalimages/currentfinal5blocks/tools/actions. DispatcherimplementationSHA changes and is recorded truthfully.
- **new packet and private memory**：pass。One CURRENT self-state text item inserted immediatelybefore original finalCURRENT, after unchangedP7detail/history. Observation/episode/time/hash provenance recorded. Original images exact; final liveinputhash/publicprojection/privacyindices updated. Privateprovideritems remainlive but savedonlyhashedredactions; fullreconstruction refused ifprivateitems exist. Intermediatepre-selfmanifest explicitlynotdelegated.
- **prompt scope and limits**：pass。P9 appends generic explanation of nominalownframes and incremental allowedtaskcontact before bottomsupport, inherits allP8/P6slip/support/release rules. NoSourceMesh/seatcoordinate/height/waypoint/expertmacro/forcedactions. P9 changesboth own-stateinformation and this promptclarification, so eventual performance cannot be called single-factorA/B. Noautomaticmotion/action/safetyoverride.
- **budget and reservation**：pass。Profile differs fromP8 only robot_self_state. Originalsameclient reserves fullaugmentedinput before exactlyonefakeHTTP; requestcount/cost/input/output/actioncaps unchanged30USD/1500/80k/1024. Counterfactualclosed06(17decisions/18attempts) and07(46/46) maxbounds71826/71661, minimum margins8174/8339; not actualP9usage nor futurecapacity/billing guarantee. Boundfailure tested beforeHTTP/action.
- **CPU scope**：pass。Reviewer130passed/0failed/0skip; authorfullXML independentlyparsed760passed/13skip/0failure/error. AuthorGit-freeXML82passed/0failure separately; reviewer didnotrerunfull/Git-free suites. NoAPI/GPU/nativeepisode validation performed.

## 保留限制

- P9 genuine API/native task notrun byreviewer; fullsuccess requiresactual standardreset workflow and originalscorer.
- Derivedframes are nominal ownmodel facts anchoredto measuredpublicTCP; not nativebodypose truth, obstacleperception or collisionfree-path proof.
- Onlylink6/link7/hand boxes; fingers/heldvessel/otherlinks remain outsidethisaddedboxscope; RGBanddeclaredsensorsstillneeded.
- Cookedshape/contactoffset/padding/sweepandrealcalibration remainunverified; numerical8decimal rounding is serialization, notprecisionclaim.
- P9 is new information/promptcondition; do not poololdP4–P8debugor callimprovementproved.
- Futureprivatecontext/modeloutput/billingunknown; retain originalledger/caps and actualclosedcall receipts.

冻结源SHA、17项保护文件、CPU命令与既有frame证明见 [review.json](review.json)。三个本体局部盒的独立USD核对见 [authored_boxes_receipt.json](authored_boxes_receipt.json)。
