"""KNX Websocket Tests."""
from typing import Any
from unittest.mock import patch

from homeassistant.components.knx import DOMAIN, KNX_ADDRESS, SwitchSchema
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant

from .conftest import FIXTURE_PROJECT_DATA, KNXTestKit

from tests.typing import WebSocketGenerator


async def test_knx_info_command(
    hass: HomeAssistant, knx: KNXTestKit, hass_ws_client: WebSocketGenerator
):
    """Test knx/info command."""
    await knx.setup_integration({})
    client = await hass_ws_client(hass)
    await client.send_json({"id": 6, "type": "knx/info"})

    res = await client.receive_json()
    assert res["success"], res
    assert res["result"]["version"] is not None
    assert res["result"]["connected"]
    assert res["result"]["current_address"] == "0.0.0"
    assert res["result"]["project"] is None


async def test_knx_info_command_with_project(
    hass: HomeAssistant,
    knx: KNXTestKit,
    hass_ws_client: WebSocketGenerator,
    load_knxproj: None,
):
    """Test knx/info command with loaded project."""
    await knx.setup_integration({})
    client = await hass_ws_client(hass)
    await client.send_json({"id": 6, "type": "knx/info"})

    res = await client.receive_json()
    assert res["success"], res
    assert res["result"]["version"] is not None
    assert res["result"]["connected"]
    assert res["result"]["current_address"] == "0.0.0"
    assert res["result"]["project"] is not None
    assert res["result"]["project"]["name"] == "Fixture"
    assert res["result"]["project"]["last_modified"] == "2023-04-30T09:04:04.4043671Z"
    assert res["result"]["project"]["tool_version"] == "5.7.1428.39779"


async def test_knx_project_file_process(
    hass: HomeAssistant,
    knx: KNXTestKit,
    hass_ws_client: WebSocketGenerator,
    hass_storage: dict[str, Any],
):
    """Test knx/project_file_process command for storing and loading new data."""
    _file_id = "1234"
    _password = "pw-test"
    _parse_result = FIXTURE_PROJECT_DATA

    await knx.setup_integration({})
    client = await hass_ws_client(hass)
    assert not hass.data[DOMAIN].project.loaded

    await client.send_json(
        {
            "id": 6,
            "type": "knx/project_file_process",
            "file_id": _file_id,
            "password": _password,
        }
    )
    with patch(
        "homeassistant.components.knx.project.process_uploaded_file",
    ) as file_upload_mock, patch(
        "xknxproject.XKNXProj.parse", return_value=_parse_result
    ) as parse_mock:
        file_upload_mock.return_value.__enter__.return_value = ""
        res = await client.receive_json()

        file_upload_mock.assert_called_once_with(hass, _file_id)
        parse_mock.assert_called_once_with()

    assert res["success"], res
    assert hass.data[DOMAIN].project.loaded


async def test_knx_project_file_process_error(
    hass: HomeAssistant,
    knx: KNXTestKit,
    hass_ws_client: WebSocketGenerator,
):
    """Test knx/project_file_process exception handling."""
    await knx.setup_integration({})
    client = await hass_ws_client(hass)
    assert not hass.data[DOMAIN].project.loaded

    await client.send_json(
        {
            "id": 6,
            "type": "knx/project_file_process",
            "file_id": "1234",
            "password": "",
        }
    )
    with patch(
        "homeassistant.components.knx.project.process_uploaded_file",
    ) as file_upload_mock, patch(
        "xknxproject.XKNXProj.parse", side_effect=ValueError
    ) as parse_mock:
        file_upload_mock.return_value.__enter__.return_value = ""
        res = await client.receive_json()
        parse_mock.assert_called_once_with()

    assert res["error"], res
    assert not hass.data[DOMAIN].project.loaded


async def test_knx_project_file_remove(
    hass: HomeAssistant,
    knx: KNXTestKit,
    hass_ws_client: WebSocketGenerator,
    load_knxproj: None,
):
    """Test knx/project_file_remove command."""
    await knx.setup_integration({})
    client = await hass_ws_client(hass)
    assert hass.data[DOMAIN].project.loaded

    await client.send_json({"id": 6, "type": "knx/project_file_remove"})
    with patch("homeassistant.helpers.storage.Store.async_remove") as remove_mock:
        res = await client.receive_json()
        remove_mock.assert_called_once_with()

    assert res["success"], res
    assert not hass.data[DOMAIN].project.loaded


async def test_knx_group_monitor_info_command(
    hass: HomeAssistant, knx: KNXTestKit, hass_ws_client: WebSocketGenerator
):
    """Test knx/group_monitor_info command."""
    await knx.setup_integration({})
    client = await hass_ws_client(hass)

    await client.send_json({"id": 6, "type": "knx/group_monitor_info"})

    res = await client.receive_json()
    assert res["success"], res
    assert res["result"]["project_loaded"] is False


async def test_knx_subscribe_telegrams_command_no_project(
    hass: HomeAssistant, knx: KNXTestKit, hass_ws_client: WebSocketGenerator
):
    """Test knx/subscribe_telegrams command without project data."""
    await knx.setup_integration(
        {
            SwitchSchema.PLATFORM: {
                CONF_NAME: "test",
                KNX_ADDRESS: "1/2/4",
            }
        }
    )
    client = await hass_ws_client(hass)
    await client.send_json({"id": 6, "type": "knx/subscribe_telegrams"})
    res = await client.receive_json()
    assert res["success"], res

    # send incoming events
    await knx.receive_read("1/2/3")
    await knx.receive_write("1/3/4", True)
    await knx.receive_write("1/3/4", False)
    await knx.receive_individual_address_read()
    await knx.receive_write("1/3/8", (0x34, 0x45))
    # send outgoing events
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.test"}, blocking=True
    )
    await knx.assert_write("1/2/4", 1)

    # receive events
    res = await client.receive_json()
    assert res["event"]["destination_address"] == "1/2/3"
    assert res["event"]["payload"] == ""
    assert res["event"]["type"] == "GroupValueRead"
    assert res["event"]["source_address"] == "1.2.3"
    assert res["event"]["direction"] == "group_monitor_incoming"
    assert res["event"]["timestamp"] is not None

    res = await client.receive_json()
    assert res["event"]["destination_address"] == "1/3/4"
    assert res["event"]["payload"] == "1"
    assert res["event"]["type"] == "GroupValueWrite"
    assert res["event"]["source_address"] == "1.2.3"
    assert res["event"]["direction"] == "group_monitor_incoming"
    assert res["event"]["timestamp"] is not None

    res = await client.receive_json()
    assert res["event"]["destination_address"] == "1/3/4"
    assert res["event"]["payload"] == "0"
    assert res["event"]["type"] == "GroupValueWrite"
    assert res["event"]["source_address"] == "1.2.3"
    assert res["event"]["direction"] == "group_monitor_incoming"
    assert res["event"]["timestamp"] is not None

    res = await client.receive_json()
    assert res["event"]["destination_address"] == "1/3/8"
    assert res["event"]["payload"] == "0x3445"
    assert res["event"]["type"] == "GroupValueWrite"
    assert res["event"]["source_address"] == "1.2.3"
    assert res["event"]["direction"] == "group_monitor_incoming"
    assert res["event"]["timestamp"] is not None

    res = await client.receive_json()
    assert res["event"]["destination_address"] == "1/2/4"
    assert res["event"]["payload"] == "1"
    assert res["event"]["type"] == "GroupValueWrite"
    assert (
        res["event"]["source_address"] == "0.0.0"
    )  # needs to be the IA currently connected to
    assert res["event"]["direction"] == "group_monitor_outgoing"
    assert res["event"]["timestamp"] is not None


async def test_knx_subscribe_telegrams_command_project(
    hass: HomeAssistant,
    knx: KNXTestKit,
    hass_ws_client: WebSocketGenerator,
    load_knxproj: None,
):
    """Test knx/subscribe_telegrams command with project data."""
    await knx.setup_integration({})
    client = await hass_ws_client(hass)
    await client.send_json({"id": 6, "type": "knx/subscribe_telegrams"})
    res = await client.receive_json()
    assert res["success"], res

    # incoming DPT 1 telegram
    await knx.receive_write("0/0/1", True)
    res = await client.receive_json()
    assert res["event"]["destination_address"] == "0/0/1"
    assert res["event"]["destination_text"] == "Binary"
    assert res["event"]["payload"] == "1"
    assert res["event"]["type"] == "GroupValueWrite"
    assert res["event"]["source_address"] == "1.2.3"
    assert res["event"]["direction"] == "group_monitor_incoming"
    assert res["event"]["timestamp"] is not None

    # incoming DPT 5 telegram
    await knx.receive_write("0/1/1", (0x50,), source="1.1.6")
    res = await client.receive_json()
    assert res["event"]["destination_address"] == "0/1/1"
    assert res["event"]["destination_text"] == "percent"
    assert res["event"]["payload"] == "0x50"
    assert res["event"]["value"] == "31 %"
    assert res["event"]["type"] == "GroupValueWrite"
    assert res["event"]["source_address"] == "1.1.6"
    assert (
        res["event"]["source_text"]
        == "Enertex Bayern GmbH Enertex KNX LED Dimmsequenzer 20A/5x REG"
    )
    assert res["event"]["direction"] == "group_monitor_incoming"
    assert res["event"]["timestamp"] is not None

    # incoming undecodable telegram (wrong payload type)
    await knx.receive_write("0/1/1", True, source="1.1.6")
    res = await client.receive_json()
    assert res["event"]["destination_address"] == "0/1/1"
    assert res["event"]["destination_text"] == "percent"
    assert res["event"]["payload"] == "1"
    assert res["event"]["value"] == "Error decoding value"
    assert res["event"]["type"] == "GroupValueWrite"
    assert res["event"]["source_address"] == "1.1.6"
    assert (
        res["event"]["source_text"]
        == "Enertex Bayern GmbH Enertex KNX LED Dimmsequenzer 20A/5x REG"
    )
    assert res["event"]["direction"] == "group_monitor_incoming"
    assert res["event"]["timestamp"] is not None
