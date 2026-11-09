# 公共模块库: 串口/协议/控制/手势/映射/UI (不碰mediapipe)
add_library(hand_common STATIC
    serial_port.cpp
    protocol.cpp
    cyberhand.cpp
    gesture.cpp
    retarget.cpp
    ui.cpp)
target_link_libraries(hand_common PUBLIC ${OpenCV_LIBS} Threads::Threads)
if(X11_FOUND)
    target_compile_definitions(hand_common PUBLIC HAVE_X11)
    target_link_libraries(hand_common PUBLIC ${X11_LIBRARIES})
endif()

# 推理模块: 全项目唯一接触mediapipe的编译单元, 独立成库方便整体替换(如换RKNN)
add_library(hand_infer STATIC hand_infer.cpp)
if(MEDIAPIPE_INCLUDE_DIR)
    target_include_directories(hand_infer PRIVATE ${MEDIAPIPE_INCLUDE_DIR})
endif()
if(MEDIAPIPE_EXTRA_INCLUDES)
    target_include_directories(hand_infer PRIVATE ${MEDIAPIPE_EXTRA_INCLUDES})
endif()
if(MEDIAPIPE_LIBS)
    target_link_libraries(hand_infer PUBLIC ${MEDIAPIPE_LIBS})
endif()
