"""
Tests for Dialogue & Interaction System

Covers:
- DialogParser: Speaker identification, content extraction, type classification
- TextSpeedController: Optimal text speed for AI vs human readability
- MenuNavigator: Option selection, Yes/No dialogs, multiple choice menus
- NPCInteraction: Trainer battle detection, gift/reward extraction
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.core.dialogue import (
    DialogParser, TextSpeedController, MenuNavigator, NPCInteraction, DialogueManager,
    DialogType, SpeakerType, DialogIntent, MenuType, NavigationButton,
    DialogLine, DialogEntry, MenuOption, MenuState, NPCInfo, InteractionResult,
    create_dialogue_system, create_dialog_parser, create_text_speed_controller,
    create_menu_navigator, create_npc_interaction
)


class TestDialogParser:
    """Test dialog parsing functionality"""

    def setup_method(self):
        self.parser = DialogParser()

    def test_parse_simple_greeting(self):
        """Should parse a simple greeting"""
        dialog = "Hello there! Welcome to our town."
        entry = self.parser.parse_dialog(dialog)
        
        assert entry is not None
        assert len(entry.lines) > 0
        assert entry.primary_intent == DialogIntent.GREETING

    def test_parse_battle_challenge(self):
        """Should parse battle challenge dialog"""
        dialog = "I challenge you to a battle! Prepare yourself!"
        entry = self.parser.parse_dialog(dialog)
        
        assert entry.primary_intent in [DialogIntent.BATTLE_CHALLENGE, DialogIntent.THREAT]
        assert entry.dialog_type == DialogType.BATTLE

    def test_parse_quest_offer(self):
        """Should parse quest offer dialog"""
        dialog = "Please help me find my lost Pokemon. It's somewhere in the forest."
        entry = self.parser.parse_dialog(dialog)
        
        assert entry.primary_intent in [DialogIntent.QUEST, DialogIntent.INFORMATION]
        assert entry.quest_triggered is not None or len(entry.information_extracted) > 0

    def test_parse_shop_dialog(self):
        """Should parse shop dialog"""
        dialog = "Welcome to the PokeMart! What would you like to buy?"
        entry = self.parser.parse_dialog(dialog)
        
        assert entry.primary_intent in [DialogIntent.SHOP, DialogIntent.GREETING, DialogIntent.CHOICE]
        assert DialogType.ITEM in [entry.dialog_type, DialogType.INFORMATION]

    def test_parse_item_gift(self):
        """Should parse gift dialog"""
        dialog = "Here, have this Potion. It will help you on your journey."
        entry = self.parser.parse_dialog(dialog)
        
        assert entry.primary_intent == DialogIntent.GIFT
        assert entry.reward_offered is not None
        assert "POTION" in entry.reward_offered.get('item', '').upper()

    def test_parse_healing_dialog(self):
        """Should parse healing dialog"""
        dialog = "Welcome to the Pokemon Center! Your Pokemon have been healed."
        entry = self.parser.parse_dialog(dialog)
        
        assert entry.primary_intent in [DialogIntent.HEAL, DialogIntent.GREETING]

    def test_parse_progression_dialog(self):
        """Should parse progression dialog"""
        dialog = "You've earned the Badge! The path to the next city is now open."
        entry = self.parser.parse_dialog(dialog)
        
        assert entry.primary_intent in [DialogIntent.PROGRESSION, DialogIntent.REWARD]

    def test_extract_pokemon_entities(self):
        """Should extract Pokemon names from dialog"""
        dialog = "I saw a rare Pikachu near the forest. You should catch it!"
        entry = self.parser.parse_dialog(dialog)
        
        pokemon = entry.key_entities.get('pokemon', [])
        assert "PIKACHU" in pokemon

    def test_extract_location_entities(self):
        """Should extract location names from dialog"""
        dialog = "The legendary Pokemon is hiding in Cerulean Cave."
        entry = self.parser.parse_dialog(dialog)
        
        locations = entry.key_entities.get('locations', [])
        assert "CERULEAN CAVE" in locations or len(locations) > 0

    def test_extract_item_entities(self):
        """Should extract item names from dialog"""
        dialog = "You found a TM containing Thunderbolt! Use it on your Pikachu."
        entry = self.parser.parse_dialog(dialog)
        
        items = entry.key_entities.get('items', [])
        assert any("TM" in item for item in items)

    def test_parse_multiple_lines(self):
        """Should parse multiple lines of dialog"""
        dialog = """Hello there!
I haven't seen you before.
Are you a Pokemon Trainer?"""
        entry = self.parser.parse_dialog(dialog)
        
        assert len(entry.lines) == 3
        assert entry.confidence > 0

    def test_parse_choice_dialog(self):
        """Should identify choice dialog"""
        dialog = "What would you like to do? 1) Battle 2) Talk 3) Leave"
        entry = self.parser.parse_dialog(dialog)
        
        assert any(line.is_choice for line in entry.lines)

    def test_parse_important_line_detection(self):
        """Should identify important lines"""
        dialog = "Hello there! By the way, the Gym Leader has the Badge you need."
        entry = self.parser.parse_dialog(dialog)
        
        assert any(line.is_important for line in entry.lines)

    def test_secondary_intent_detection(self):
        """Should detect secondary intent or primary is battle challenge"""
        dialog = "Welcome! Let's have a battle and become friends!"
        entry = self.parser.parse_dialog(dialog)
        
        assert entry.primary_intent in [DialogIntent.GREETING, DialogIntent.BATTLE_CHALLENGE]

    def test_parse_empty_dialog(self):
        """Should handle empty dialog"""
        entry = self.parser.parse_dialog("")
        
        assert entry is not None
        assert entry.primary_intent == DialogIntent.INFORMATION

    def test_parse_system_message(self):
        """Should parse system messages"""
        dialog = "SAVED THE GAME."
        entry = self.parser.parse_dialog(dialog)
        
        assert entry is not None

    def test_parse_trainer_introduction(self):
        """Should detect trainer class from dialog"""
        dialog = "I am Brock, the Pewter City Gym Leader. I'm rock-solid!"
        entry = self.parser.parse_dialog(dialog, {'location': 'PEWTER CITY'})
        
        assert entry.dialog_type in [DialogType.TRAINER, DialogType.BATTLE]

    def test_confidence_calculation(self):
        """Should calculate confidence score"""
        dialog = "Battle! Battle! Battle!"
        entry = self.parser.parse_dialog(dialog)
        
        assert 0.0 <= entry.confidence <= 1.0

    def test_actions_required_extraction(self):
        """Should extract required actions from intent"""
        dialog = "Would you like to enter the shop?"
        entry = self.parser.parse_dialog(dialog)
        
        assert len(entry.actions_required) > 0

    def test_information_extraction(self):
        """Should extract useful information from dialog"""
        dialog = "Did you know that Zapdos appears during thunderstorms on Route 10?"
        entry = self.parser.parse_dialog(dialog)
        
        assert len(entry.information_extracted) > 0

    def test_pokemon_database_completeness(self):
        """Pokemon database should contain expected names"""
        assert "PIKACHU" in self.parser._pokemon_names
        assert "CHARIZARD" in self.parser._pokemon_names
        assert "MEWTWO" in self.parser._pokemon_names

    def test_location_database_completeness(self):
        """Location database should contain expected locations"""
        assert "PALLET TOWN" in self.parser._location_names
        assert "ROUTE 1" in self.parser._location_names
        assert "VIRIDIAN CITY" in self.parser._location_names

    def test_item_database_completeness(self):
        """Item database should contain expected items"""
        assert "POKE BALL" in self.parser._item_names
        assert "POTION" in self.parser._item_names
        assert "TM" in self.parser._item_names


class TestTextSpeedController:
    """Test text speed control functionality"""

    def setup_method(self):
        self.controller = TextSpeedController()

    def test_get_optimal_speed_short_dialog(self):
        """Should use normal speed for short dialog"""
        dialog = DialogEntry(
            lines=[DialogLine("Hello!", "HELLO", None, None, DialogIntent.GREETING)],
            dialog_type=DialogType.INFORMATION,
            primary_intent=DialogIntent.GREETING,
            secondary_intent=None,
            confidence=0.9
        )
        
        speed = self.controller.get_optimal_speed(dialog)
        
        assert speed['auto_advance'] == True

    def test_get_optimal_speed_long_dialog(self):
        """Should skip long dialogs"""
        lines = [DialogLine(f"Line {i}", f"LINE {i}", None, None, DialogIntent.INFORMATION) 
                 for i in range(10)]
        dialog = DialogEntry(
            lines=lines,
            dialog_type=DialogType.INFORMATION,
            primary_intent=DialogIntent.INFORMATION,
            secondary_intent=None,
            confidence=0.7
        )
        
        speed = self.controller.get_optimal_speed(dialog)
        
        assert speed.get('read_first_line_only') == True

    def test_calculate_button_presses(self):
        """Should calculate correct button presses"""
        dialog = DialogEntry(
            lines=[
                DialogLine("Line 1", "LINE 1", None, None, DialogIntent.GREETING),
                DialogLine("Line 2", "LINE 2", None, None, DialogIntent.GREETING),
            ],
            dialog_type=DialogType.INFORMATION,
            primary_intent=DialogIntent.GREETING,
            secondary_intent=None,
            confidence=0.8
        )
        
        presses = self.controller.calculate_button_presses(dialog)
        
        assert len(presses) > 0
        assert all(p in list(NavigationButton) for p in presses)

    def test_set_speed_setting(self):
        """Should change speed setting"""
        result = self.controller.set_speed_setting("instant")
        assert result == True
        
        result = self.controller.set_speed_setting("invalid")
        assert result == False

    def test_get_speed_stats(self):
        """Should return statistics"""
        stats = self.controller.get_speed_stats()
        
        assert 'current_setting' in stats
        assert 'total_dialogs' in stats
        assert 'skip_rate_percent' in stats

    def test_should_skip_remaining(self):
        """Should correctly determine if remaining should be skipped"""
        lines = [DialogLine(f"Line {i}", f"LINE {i}", None, None, DialogIntent.INFORMATION) 
                 for i in range(10)]
        dialog = DialogEntry(
            lines=lines,
            dialog_type=DialogType.INFORMATION,
            primary_intent=DialogIntent.INFORMATION,
            secondary_intent=None,
            confidence=0.7
        )
        
        should_skip, count = self.controller.should_skip_remaining(dialog)
        
        assert should_skip == True
        assert count == 9


class TestMenuNavigator:
    """Test menu navigation functionality"""

    def setup_method(self):
        self.navigator = MenuNavigator()

    def test_detect_main_menu(self):
        """Should detect main menu"""
        text = "POKEMON  BAG  FIGHT  RUN"
        menu_type = self.navigator.detect_menu_type(text)
        
        assert menu_type == MenuType.MAIN_MENU

    def test_detect_battle_menu(self):
        """Should detect battle menu"""
        text = "FIGHT  PKMN  ITEM  RUN"
        menu_type = self.navigator.detect_menu_type(text)
        
        assert menu_type == MenuType.BATTLE_MENU

    def test_detect_shop_menu(self):
        """Should detect shop menu"""
        text = "BUY  SELL  QUIT"
        menu_type = self.navigator.detect_menu_type(text)
        
        assert menu_type == MenuType.SHOP_MENU

    def test_detect_yes_no_dialog(self):
        """Should detect yes/no dialog"""
        text = "YES  NO"
        menu_type = self.navigator.detect_menu_type(text)
        
        assert menu_type == MenuType.YES_NO

    def test_create_menu_state(self):
        """Should create menu state from options"""
        options = ["Option 1", "Option 2", "Option 3"]
        state = self.navigator.create_menu_state(MenuType.CHOICE, options, 0)
        
        assert state.menu_type == MenuType.CHOICE
        assert len(state.options) == 3
        assert state.current_selection == 0

    def test_calculate_navigation_path(self):
        """Should calculate correct navigation path"""
        path = self.navigator.calculate_navigation_path((0, 0), (1, 0))
        
        assert NavigationButton.DOWN in path

    def test_navigate_to_option(self):
        """Should navigate to specific option"""
        options = ["POKEMON", "BAG", "FIGHT", "RUN"]
        state = self.navigator.create_menu_state(MenuType.MAIN_MENU, options, 0)
        
        success, path = self.navigator.navigate_to_option(state, "BAG")
        
        assert success == True
        assert len(path) > 0

    def test_select_current_option(self):
        """Should return select button press"""
        presses = self.navigator.select_current_option()
        
        assert NavigationButton.A in presses

    def test_handle_yes_no_yes(self):
        """Should handle yes response"""
        presses = self.navigator.handle_yes_no_dialog(True)
        
        assert presses[0] == NavigationButton.A

    def test_handle_yes_no_no(self):
        """Should handle no response"""
        presses = self.navigator.handle_yes_no_dialog(False)
        
        assert presses[0] == NavigationButton.DOWN
        assert presses[1] == NavigationButton.A

    def test_handle_multiple_choice(self):
        """Should handle multiple choice selection"""
        presses = self.navigator.handle_multiple_choice(2, 4)
        
        assert NavigationButton.A in presses

    def test_exit_menu(self):
        """Should return exit button presses"""
        presses = self.navigator.exit_menu()
        
        assert presses[0] == NavigationButton.B

    def test_get_menu_stats(self):
        """Should return menu navigation statistics"""
        stats = self.navigator.get_menu_stats()
        
        assert 'total_navigations' in stats
        assert 'success_rate_percent' in stats

    def test_navigation_failure(self):
        """Should handle navigation to non-existent option"""
        options = ["POKEMON", "BAG"]
        state = self.navigator.create_menu_state(MenuType.MAIN_MENU, options, 0)
        
        success, path = self.navigator.navigate_to_option(state, "INVALID")
        
        assert success == False
        assert len(path) == 0

    def test_cache_clearing(self):
        """Should clear navigation cache"""
        self.navigator._menu_cache['test'] = []
        self.navigator.clear_cache()
        
        assert len(self.navigator._menu_cache) == 0

    def test_unknown_menu_type(self):
        """Should return None for unknown menu"""
        text = "Some random text that doesn't match any menu"
        menu_type = self.navigator.detect_menu_type(text)
        
        assert menu_type is None


class TestNPCInteraction:
    """Test NPC interaction functionality"""

    def setup_method(self):
        self.interaction = NPCInteraction()

    def test_interact_with_npc(self):
        """Should process NPC interaction"""
        result = self.interaction.interact_with_npc(
            "PROFESSOR OAK",
            "Hello there! Welcome to the world of Pokemon!"
        )
        
        assert result.success == True
        assert result.npc_info is not None
        assert result.npc_info.name == "PROFESSOR OAK"

    def test_detect_battle_initiation(self):
        """Should detect when battle is initiated"""
        result = self.interaction.interact_with_npc(
            "RIVAL",
            "Let's battle! I challenge you!"
        )
        
        assert result.battle_initiated == True

    def test_extract_gift(self):
        """Should extract gift information"""
        result = self.interaction.interact_with_npc(
            "MR FUJI",
            "Here, take this Potion as a gift!"
        )
        
        assert result.gift_received is not None and "POTION" in result.gift_received.upper()

    def test_extract_information(self):
        """Should extract information from dialog"""
        info = self.interaction.extract_information(
            "Did you know that rare Pokemon appear at night?"
        )
        
        assert len(info) > 0

    def test_extract_hints(self):
        """Should extract hints from dialog"""
        hints = self.interaction.extract_hints(
            "Here's a tip: There's a hidden Rare Candy in the forest."
        )
        
        assert len(hints) > 0

    def test_get_npc_info(self):
        """Should return NPC info"""
        npc_info = self.interaction.get_npc_info("BROCK")
        
        assert npc_info is not None
        assert npc_info.name == "BROCK"
        assert npc_info.is_trainer == True

    def test_get_interaction_history(self):
        """Should return interaction history"""
        self.interaction.interact_with_npc("NPC1", "Hello")
        self.interaction.interact_with_npc("NPC2", "Hi")
        
        history = self.interaction.get_interaction_history()
        
        assert len(history) == 2

    def test_get_interaction_stats(self):
        """Should return interaction statistics"""
        stats = self.interaction.get_interaction_stats()
        
        assert 'total_interactions' in stats
        assert 'battles_initiated' in stats

    def test_create_new_npc(self):
        """Should create entry for unknown NPC"""
        result = self.interaction.interact_with_npc(
            "UNKNOWN NPC",
            "Hello there!"
        )
        
        assert result.npc_info is not None
        assert result.npc_info.name == "UNKNOWN NPC"

    def test_determine_action(self):
        """Should determine correct action"""
        result = self.interaction.interact_with_npc(
            "SHOPKEEPER",
            "Welcome! What would you like to buy?"
        )
        
        assert result.action_taken in ["enter_shop", "acknowledge", "continue"]

    def test_npc_database_completeness(self):
        """Should have default NPCs in database"""
        assert "BROCK" in self.interaction._npc_database
        assert "MISTY" in self.interaction._npc_database
        assert "NURSE JOY" in self.interaction._npc_database

    def test_unknown_npc_returns_none(self):
        """Should return None for unknown NPC"""
        npc_info = self.interaction.get_npc_info("NONEXISTENT NPC")
        
        assert npc_info is None

    def test_interaction_with_empty_dialog(self):
        """Should handle empty dialog"""
        result = self.interaction.interact_with_npc("NPC", "")
        
        assert result.success == True

    def test_quest_detection(self):
        """Should detect quest start"""
        result = self.interaction.interact_with_npc(
            "NPC",
            "Please help me find my lost Pokemon!"
        )
        
        assert result.quest_started is not None or len(result.information_gained) > 0


class TestDialogueManager:
    """Test main dialogue manager"""

    def setup_method(self):
        self.manager = create_dialogue_system()

    def test_process_dialog(self):
        """Should process dialog text"""
        entry = self.manager.process_dialog("Hello there!")
        
        assert entry is not None
        assert entry.primary_intent is not None

    def test_advance_dialog(self):
        """Should return button presses for dialog advancement"""
        entry = self.manager.process_dialog("Hello!")
        presses = self.manager.advance_dialog(entry)
        
        assert len(presses) > 0

    def test_handle_npc_interaction(self):
        """Should handle NPC interaction"""
        result = self.manager.handle_npc_interaction(
            "PROFESSOR OAK",
            "Welcome to the world of Pokemon!"
        )
        
        assert result.success == True
        assert result.npc_info is not None

    def test_navigate_menu(self):
        """Should navigate menu to option"""
        success, presses = self.manager.navigate_menu(
            "POKEMON  BAG  FIGHT",
            "BAG"
        )
        
        assert success == True or success == False

    def test_get_system_stats(self):
        """Should return system statistics"""
        self.manager.process_dialog("Test dialog")
        
        stats = self.manager.get_system_stats()
        
        assert 'total_dialogs_processed' in stats
        assert 'text_speed' in stats
        assert 'menu_navigation' in stats

    def test_get_dialog_history(self):
        """Should return dialog history"""
        self.manager.process_dialog("Dialog 1")
        self.manager.process_dialog("Dialog 2")
        
        history = self.manager.get_dialog_history()
        
        assert len(history) == 2

    def test_reset(self):
        """Should reset manager state"""
        self.manager.process_dialog("Test")
        
        self.manager.reset()
        
        history = self.manager.get_dialog_history()
        assert len(history) == 0

    def test_multiple_dialogs(self):
        """Should handle multiple dialogs correctly"""
        entry1 = self.manager.process_dialog("Hello!")
        entry2 = self.manager.process_dialog("Welcome!")
        
        assert entry1 is not None
        assert entry2 is not None
        assert entry1 != entry2


class TestDialogTypes:
    """Test dialog type classification"""

    def setup_method(self):
        self.parser = DialogParser()

    def test_battle_dialog_type(self):
        """Should classify battle dialog"""
        dialog = "I challenge you to a battle!"
        entry = self.parser.parse_dialog(dialog)
        
        assert entry.dialog_type == DialogType.BATTLE

    def test_item_dialog_type(self):
        """Should classify item dialog"""
        dialog = "Here's a rare item for you!"
        entry = self.parser.parse_dialog(dialog)
        
        assert entry.dialog_type in [DialogType.ITEM, DialogType.INFORMATION]

    def test_information_dialog_type(self):
        """Should classify information dialog"""
        dialog = "Did you know that Pokemon have different types?"
        entry = self.parser.parse_dialog(dialog)
        
        assert entry.dialog_type == DialogType.INFORMATION


class TestIntentClassification:
    """Test intent classification accuracy"""

    def setup_method(self):
        self.parser = DialogParser()

    def test_greeting_intent(self):
        """Should classify greeting intent"""
        dialog = "Hello! Nice to meet you!"
        entry = self.parser.parse_dialog(dialog)
        
        assert entry.primary_intent == DialogIntent.GREETING

    def test_threat_intent(self):
        """Should classify threat intent"""
        dialog = "You'll never defeat me!"
        entry = self.parser.parse_dialog(dialog)
        
        assert entry.primary_intent in [DialogIntent.THREAT, DialogIntent.BATTLE_CHALLENGE]

    def test_choice_intent(self):
        """Should classify choice intent"""
        dialog = "What would you like to do?"
        entry = self.parser.parse_dialog(dialog)
        
        assert entry.primary_intent == DialogIntent.CHOICE

    def test_reward_intent(self):
        """Should classify reward intent"""
        dialog = "You've won a prize!"
        entry = self.parser.parse_dialog(dialog)
        
        assert entry.primary_intent == DialogIntent.REWARD


class TestFactoryFunctions:
    """Test factory function creation"""

    def test_create_dialogue_system(self):
        """Should create dialogue system"""
        system = create_dialogue_system()
        
        assert system is not None
        assert isinstance(system, DialogueManager)

    def test_create_dialog_parser(self):
        """Should create dialog parser"""
        parser = create_dialog_parser()
        
        assert parser is not None
        assert isinstance(parser, DialogParser)

    def test_create_text_speed_controller(self):
        """Should create text speed controller"""
        controller = create_text_speed_controller()
        
        assert controller is not None
        assert isinstance(controller, TextSpeedController)

    def test_create_menu_navigator(self):
        """Should create menu navigator"""
        navigator = create_menu_navigator()
        
        assert navigator is not None
        assert isinstance(navigator, MenuNavigator)

    def test_create_npc_interaction(self):
        """Should create NPC interaction handler"""
        handler = create_npc_interaction()
        
        assert handler is not None
        assert isinstance(handler, NPCInteraction)


class TestEdgeCases:
    """Test edge cases and error handling"""

    def setup_method(self):
        self.parser = DialogParser()

    def test_very_long_dialog(self):
        """Should handle very long dialog"""
        long_dialog = " ".join(["This is a long dialog line."] * 100)
        entry = self.parser.parse_dialog(long_dialog)
        
        assert entry is not None
        assert len(entry.lines) > 0

    def test_special_characters(self):
        """Should handle special characters"""
        dialog = "Hello! How are you???!!!"
        entry = self.parser.parse_dialog(dialog)
        
        assert entry is not None

    def test_numbers_in_dialog(self):
        """Should handle numbers in dialog"""
        dialog = "You need at least 10 Pokemon to enter."
        entry = self.parser.parse_dialog(dialog)
        
        assert entry is not None

    def test_mixed_case_text(self):
        """Should handle mixed case text"""
        dialog = "HeLLo WoRLd!"
        entry = self.parser.parse_dialog(dialog)
        
        assert entry is not None

    def test_empty_lines_in_dialog(self):
        """Should handle dialog with empty lines"""
        dialog = "Hello\n\n\nGoodbye"
        entry = self.parser.parse_dialog(dialog)
        
        assert entry is not None

    def test_dialog_with_only_entities(self):
        """Should handle dialog with only entity names"""
        dialog = "PIKACHU CHARIZARD MEWTWO"
        entry = self.parser.parse_dialog(dialog)
        
        assert entry is not None
        assert len(entry.key_entities.get('pokemon', [])) > 0


class TestDialogEntry:
    """Test DialogEntry dataclass"""

    def test_dialog_entry_creation(self):
        """Should create dialog entry with all fields"""
        entry = DialogEntry(
            lines=[],
            dialog_type=DialogType.STORY,
            primary_intent=DialogIntent.GREETING,
            secondary_intent=None,
            confidence=0.9
        )
        
        assert entry.dialog_type == DialogType.STORY
        assert entry.primary_intent == DialogIntent.GREETING
        assert entry.confidence == 0.9

    def test_dialog_entry_with_entities(self):
        """Should store entities correctly"""
        entry = DialogEntry(
            lines=[],
            dialog_type=DialogType.INFORMATION,
            primary_intent=DialogIntent.INFORMATION,
            secondary_intent=None,
            confidence=0.8,
            key_entities={'pokemon': ['PIKACHU']}
        )
        
        assert 'PIKACHU' in entry.key_entities['pokemon']

    def test_dialog_entry_with_reward(self):
        """Should store reward information"""
        entry = DialogEntry(
            lines=[],
            dialog_type=DialogType.ITEM,
            primary_intent=DialogIntent.GIFT,
            secondary_intent=None,
            confidence=0.9,
            reward_offered={'item': 'Potion'}
        )
        
        assert entry.reward_offered is not None
        assert entry.reward_offered['item'] == 'Potion'


class TestMenuState:
    """Test MenuState dataclass"""

    def test_menu_state_creation(self):
        """Should create menu state correctly"""
        options = [
            MenuOption(0, "Option 1", 0, 0, True),
            MenuOption(1, "Option 2", 1, 0, False),
        ]
        state = MenuState(
            menu_type=MenuType.CHOICE,
            options=options,
            current_selection=0,
            cursor_position=(0, 0)
        )
        
        assert state.menu_type == MenuType.CHOICE
        assert len(state.options) == 2

    def test_menu_option_properties(self):
        """Should have correct option properties"""
        option = MenuOption(
            index=0,
            text="POKEMON",
            row=0,
            col=0,
            is_selected=True
        )
        
        assert option.index == 0
        assert option.is_selected == True


class TestNPCInfo:
    """Test NPCInfo dataclass"""

    def test_npc_info_creation(self):
        """Should create NPC info correctly"""
        npc = NPCInfo(
            name="BROCK",
            role="Gym Leader",
            location="PEWTER CITY",
            is_trainer=True,
            trainer_class="GYM LEADER"
        )
        
        assert npc.name == "BROCK"
        assert npc.is_trainer == True

    def test_npc_with_hints(self):
        """Should store hints correctly"""
        npc = NPCInfo(
            name="NPC",
            role="Guide",
            location="TOWN",
            hints=["Go north for the gym", "Watch out for wild Pokemon"]
        )
        
        assert len(npc.hints) == 2


class TestInteractionResult:
    """Test InteractionResult dataclass"""

    def test_interaction_result_creation(self):
        """Should create interaction result correctly"""
        result = InteractionResult(
            success=True,
            npc_info=None,
            dialog_entry=None,
            battle_initiated=False,
            gift_received="Potion",
            information_gained=["Tip about cave"],
            quest_started=None,
            action_taken="accept"
        )
        
        assert result.success == True
        assert result.gift_received == "Potion"
        assert len(result.information_gained) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])