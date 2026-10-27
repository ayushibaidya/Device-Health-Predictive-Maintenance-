add_library(device_health_lifecycle INTERFACE)
target_include_directories(device_health_lifecycle INTERFACE include)
target_compile_features(device_health_lifecycle INTERFACE cxx_std_20)

add_library(device_health_simulation STATIC src/simulator.cpp src/telemetry_json.cpp)
target_link_libraries(device_health_simulation
    PUBLIC device_health_lifecycle
    PRIVATE nlohmann_json::nlohmann_json)

add_executable(device_simulator src/main.cpp)
target_link_libraries(device_simulator PRIVATE device_health_simulation)

set(simulator_targets device_health_simulation device_simulator)

if(BUILD_TESTING)
    add_executable(device_lifecycle_tests tests/device_state_test.cpp)
    target_link_libraries(device_lifecycle_tests PRIVATE device_health_lifecycle)

    foreach(test_case IN ITEMS progression recovery skipped_states terminal invalid_state)
        add_test(
            NAME simulator.lifecycle.${test_case}
            COMMAND device_lifecycle_tests ${test_case})
    endforeach()

    add_executable(simulator_tests tests/simulator_test.cpp)
    target_link_libraries(simulator_tests PRIVATE
        device_health_simulation nlohmann_json::nlohmann_json)
    foreach(test_case IN ITEMS thresholds recovery interrupted_recovery
            fault_blocks_recovery custom_configuration reset
            reproducibility schema invalid_sample time configuration)
        add_test(NAME simulator.model.${test_case}
            COMMAND simulator_tests ${test_case})
    endforeach()

    add_executable(simulator_output_tests tests/simulator_output_test.cpp)
    target_link_libraries(simulator_output_tests PRIVATE
        device_health_simulation nlohmann_json::nlohmann_json)
    list(APPEND simulator_targets device_lifecycle_tests simulator_tests simulator_output_tests)

    foreach(mode IN ITEMS default reset)
        add_test(NAME simulator.cli.${mode}
            COMMAND "${CMAKE_COMMAND}"
                "-DSIMULATOR=$<TARGET_FILE:device_simulator>"
                "-DVALIDATOR=$<TARGET_FILE:simulator_output_tests>"
                "-DOUTPUT_DIR=${CMAKE_CURRENT_BINARY_DIR}/cli-${mode}"
                "-DMODE=${mode}"
                -P "${CMAKE_CURRENT_SOURCE_DIR}/tests/cli_contract.cmake")
    endforeach()

    add_test(NAME simulator.cli.help COMMAND device_simulator --help)
    set_tests_properties(simulator.cli.help PROPERTIES
        PASS_REGULAR_EXPRESSION "Usage: device_simulator")
    add_test(NAME simulator.cli.accelerated_clock
        COMMAND device_simulator --steps 1 --speed 1000)

    foreach(test_case IN ITEMS negative_steps overflow_seed bad_date unknown_option
            missing_value duplicate_option nan_speed negative_speed slow_speed
            zero_degradation threshold_order zero_hold reset_outside clock_overflow
            zero_reset huge_steps skip_states)
        add_test(NAME simulator.cli.reject_${test_case}
            COMMAND "${CMAKE_COMMAND}"
                "-DSIMULATOR=$<TARGET_FILE:device_simulator>"
                "-DCASE=${test_case}"
                -P "${CMAKE_CURRENT_SOURCE_DIR}/tests/cli_failure.cmake")
    endforeach()

    set_tests_properties(simulator.cli.default simulator.cli.reset
        PROPERTIES TIMEOUT 30)
    add_custom_target(simulator_demo
        COMMAND "${CMAKE_COMMAND}"
            "-DSIMULATOR=$<TARGET_FILE:device_simulator>"
            "-DVALIDATOR=$<TARGET_FILE:simulator_output_tests>"
            "-DOUTPUT_DIR=${CMAKE_CURRENT_BINARY_DIR}/demo"
            -DMODE=default
            -P "${CMAKE_CURRENT_SOURCE_DIR}/tests/cli_contract.cmake"
        DEPENDS device_simulator simulator_output_tests
        COMMENT "Run and verify the three-device simulator demo"
        VERBATIM)
endif()

if(CMAKE_CXX_COMPILER_ID MATCHES "Clang|GNU")
    foreach(target IN LISTS simulator_targets)
        target_compile_options(${target} PRIVATE -Wall -Wextra -Wpedantic -Werror)
    endforeach()
endif()
