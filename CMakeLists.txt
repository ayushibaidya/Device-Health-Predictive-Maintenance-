cmake_minimum_required(VERSION 4.4.3)

project(device_health LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

include(CTest)
include(cmake/Dependencies.cmake)
add_subdirectory(simulator)

option(DEVICE_HEALTH_WITH_KAFKA "Build the approved Kafka publisher" OFF)
if(DEVICE_HEALTH_WITH_KAFKA)
    add_subdirectory(kafka)
endif()
