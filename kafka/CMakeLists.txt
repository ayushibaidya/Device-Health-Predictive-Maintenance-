find_package(PkgConfig REQUIRED)
pkg_check_modules(RDKAFKA REQUIRED IMPORTED_TARGET rdkafka=2.15.1)

add_library(device_health_kafka STATIC src/event.cpp src/publisher.cpp)
target_include_directories(device_health_kafka PUBLIC include)
target_link_libraries(device_health_kafka
    PUBLIC device_health_simulation
    PRIVATE PkgConfig::RDKAFKA nlohmann_json::nlohmann_json)
target_link_libraries(device_simulator PRIVATE device_health_kafka)
target_compile_definitions(device_simulator PRIVATE DEVICE_HEALTH_KAFKA_ENABLED=1)
if(CMAKE_CXX_COMPILER_ID MATCHES "Clang|GNU")
    target_compile_options(device_health_kafka PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()

if(BUILD_TESTING)
    add_executable(kafka_event_tests tests/event_test.cpp)
    target_link_libraries(kafka_event_tests PRIVATE device_health_kafka nlohmann_json::nlohmann_json)
    target_include_directories(kafka_event_tests PRIVATE "${PROJECT_SOURCE_DIR}/simulator/tests")
    add_test(NAME kafka.event_identity COMMAND kafka_event_tests)
    add_test(NAME kafka.failed_send_is_explicit
        COMMAND "${CMAKE_COMMAND}" "-DSIMULATOR=$<TARGET_FILE:device_simulator>"
            -P "${CMAKE_CURRENT_SOURCE_DIR}/tests/producer_failure.cmake")
endif()
