include(FetchContent)

set(DEVICE_HEALTH_JSON_ARCHIVE "" CACHE FILEPATH
    "Optional local copy of the pinned nlohmann/json release archive")
set(json_archive_url
    "https://github.com/nlohmann/json/releases/download/v3.12.0/json.tar.xz")
if(DEVICE_HEALTH_JSON_ARCHIVE)
    if(NOT EXISTS "${DEVICE_HEALTH_JSON_ARCHIVE}")
        message(FATAL_ERROR "DEVICE_HEALTH_JSON_ARCHIVE does not exist")
    endif()
    set(json_archive_url "${DEVICE_HEALTH_JSON_ARCHIVE}")
endif()

set(JSON_BuildTests OFF CACHE BOOL "Build upstream JSON tests" FORCE)
set(JSON_Install OFF CACHE BOOL "Install upstream JSON package" FORCE)
FetchContent_Declare(nlohmann_json
    URL "${json_archive_url}"
    URL_HASH SHA256=42f6e95cad6ec532fd372391373363b62a14af6d771056dbfc86160e6dfff7aa
    DOWNLOAD_EXTRACT_TIMESTAMP TRUE)
FetchContent_MakeAvailable(nlohmann_json)
