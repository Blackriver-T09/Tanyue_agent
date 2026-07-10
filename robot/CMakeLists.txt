cmake_minimum_required(VERSION 3.16)
project(tanyue_g1_robot_actions LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(UNITREE_SDK2_DIR "" CACHE PATH "Path to the Unitree SDK2 C++ installation")
if(NOT UNITREE_SDK2_DIR)
  message(FATAL_ERROR "Set -DUNITREE_SDK2_DIR=/path/to/unitree_sdk2")
endif()

find_library(UNITREE_SDK2_LIBRARY unitree_sdk2 PATHS "${UNITREE_SDK2_DIR}/lib" REQUIRED)
find_library(DDS_LIBRARY ddsc PATHS "${UNITREE_SDK2_DIR}/lib" REQUIRED)

add_executable(g1_trump_accordion g1_trump_accordion_example.cpp)
target_include_directories(g1_trump_accordion PRIVATE "${UNITREE_SDK2_DIR}/include")
target_link_libraries(g1_trump_accordion PRIVATE ${UNITREE_SDK2_LIBRARY} ${DDS_LIBRARY})

if(UNIX)
  target_link_libraries(g1_trump_accordion PRIVATE pthread)
endif()
