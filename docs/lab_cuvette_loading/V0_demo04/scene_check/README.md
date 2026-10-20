# V0_demo04 最终静态场景检查

本目录来自 `static_final_01/trial_00` 的实际 Isaac Sim 加载与 reset 检查。任务物理步数为 **0**，不能当作自然落稳、抓取或插入成功证据。

- `final_static_overview.png`：单台仪器、完整来源架和机械臂整体关系。手爪、架体与仪器可见，机械臂顶部被画面裁切。
- `final_static_top.png`：整机朝向与架体位置。整机 yaw=135°，来源架 yaw=−45°，并非只转相机。
- `final_static_source.png`：36 个开口、白色目标器皿与蓝色邻近器皿。器皿横向12.5 mm，架孔16 mm仍为暂定参数。
- `final_static_chamber.png`：开盖样品腔与两个原内部座；没有16 mm适配座。
- `final_static_static_validation.json`：实际数量、reset和朝向检查全部通过。其几何门控并未通过，见 `final_static_geometry_preflight.json`。
- `reference_video_initial_roles.jpg` 与 `reference_video_internal_seats.jpg`：从历史demo02已提取的真实参考视频截图复制，来源和哈希见清单。旧参考含邻近仪器，demo04按最新要求仅保留一台。

摄像机视角不同，屏幕中的近角/远角不能直接互换；槽位ID及世界坐标定义对应关系。静态外观检查不代表真实尺寸校准，也不能排除原座局部凸起的几何相交。
