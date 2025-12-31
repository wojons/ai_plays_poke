"""PTP-01X Exception Hierarchy

This module defines a complete exception hierarchy for the Pokémon AI system.
All custom exceptions inherit from PokemonAIError, enabling comprehensive
error handling and debugging across the entire codebase.

Usage:
    try:
        # operation that may raise an exception
        result = some_operation()
    except VisionError as e:
        # Handle vision-specific errors
        logger.error(f"Vision processing failed: {e}")
        fallback_to_heuristic()
    except PokemonAIError as e:
        # Handle any PTP-01X error
        logger.critical(f"System error: {e}")
        trigger_failsafe()

Exception Hierarchy:
    PokemonAIError (base)
    ├── ROMError
    ├── APIError
    ├── NetworkError
    ├── DatabaseError
    ├── VisionError
    ├── StateMachineError
    ├── CombatError
    ├── MemoryError
    ├── NavigationError
    ├── DialogueError
    ├── EntityError
    └── ConfigurationError
"""


class PokemonAIError(Exception):
    """Base exception for all PTP-01X errors.
    
    This is the root exception class for the entire Pokémon AI system.
    All custom exceptions should inherit from this class to enable
    comprehensive error handling at any level of the application.
    
    This exception should be raised when an error occurs that is specific
    to the PTP-01X system and doesn't fit into a more specific category.
    
    Attributes:
        message (str): Human-readable description of the error
        code (Optional[int]): Optional error code for programmatic handling
        context (dict): Additional context information about the error
    
    Example:
        try:
            validate_game_state(state)
        except ValueError as e:
            raise PokemonAIError(
                f"Invalid game state: {e}",
                code=1001,
                context={"state": state}
            )
    """
    
    def __init__(self, message: str = "An unspecified PTP-01X error occurred", code: int | None = None, **context):
        """Initialize PokemonAIError with message, code, and context.
        
        Args:
            message: Human-readable description of the error
            code: Optional error code for programmatic handling
            **context: Additional keyword arguments stored as context
        """
        super().__init__(message)
        self.message = message
        self.code = code
        self.context = context


class ROMError(PokemonAIError):
    """ROM validation and loading errors.
    
    Raised when issues occur during ROM file validation, loading, or
    compatibility checking. This includes checksum failures, unsupported
    ROM versions, corrupted ROM files, and file system access errors.
    
    Common scenarios:
        - ROM file not found or cannot be read
        - ROM checksum validation fails
        - ROM is not a supported Pokémon game version
        - ROM file is corrupted or incomplete
        - Memory-mapped file access fails
    
    Example:
        try:
            rom = load_rom(rom_path)
            if not validate_rom_header(rom):
                raise ROMError("Unsupported ROM version: expected Pokemon Yellow")
        except FileNotFoundError:
            raise ROMError(f"ROM file not found: {rom_path}")
    """
    pass


class APIError(PokemonAIError):
    """API key and API call errors.
    
    Raised when issues occur with external API interactions, including
    authentication failures, rate limiting, invalid requests, and
    response parsing errors.
    
    Common scenarios:
        - Missing or invalid API key
        - API rate limit exceeded
        - Invalid request parameters
        - API response parsing fails
        - API returns error status code
        - Token expired or revoked
    
    Example:
        try:
            response = api_client.complete(prompt)
            if response.status_code == 401:
                raise APIError("API authentication failed - check API key")
            elif response.status_code == 429:
                raise APIError("Rate limit exceeded", code=429)
        except JSONDecodeError as e:
            raise APIError(f"Failed to parse API response: {e}")
    """
    pass


class NetworkError(PokemonAIError):
    """Network connectivity errors.
    
    Raised when network-related issues prevent communication with
    external services or network-dependent operations. This includes
        - DNS resolution failures
        - Connection timeouts
        - Socket errors
        - SSL/TLS certificate issues
        - Firewall blocking
        - Unreachable hosts
    
    Example:
        try:
            await client.connect(host, port, timeout=30)
        except socket.timeout:
            raise NetworkError(
                f"Connection to {host}:{port} timed out",
                code=1001,
                host=host,
                port=port
            )
        except ssl.SSLError:
            raise NetworkError("SSL certificate validation failed")
    """
    pass


class DatabaseError(PokemonAIError):
    """Database operations errors.
    
    Raised when issues occur during database operations including
    query execution, schema management, connection handling, and
    data integrity violations.
    
    Common scenarios:
        - Database connection fails
        - Query syntax error
        - Constraint violation
        - Transaction rollback
        - Schema mismatch
        - Migration failure
        - Disk space exhaustion
    
    Example:
        try:
            with database.transaction():
                database.execute(query)
        except sqlite3.IntegrityError as e:
            raise DatabaseError(
                f"Data integrity violation: {e}",
                code=23000,
                query=query
            )
        except sqlite3.OperationalError as e:
            raise DatabaseError(f"Database operation failed: {e}")
    """
    pass


class VisionError(PokemonAIError):
    """Vision processing errors.
    
    Raised when issues occur during screen capture, image processing,
    OCR operations, or visual recognition tasks.
    
    Common scenarios:
        - Screenshot capture fails
        - Image format not supported
        - OCR text extraction fails
        - Screen classification uncertain
        - Template matching fails
        - Color threshold invalid
        - Memory error during image processing
    
    Example:
        try:
            screenshot = capture_screen()
            result = ocr.extract_text(screenshot)
            if result.confidence < 0.5:
                raise VisionError(
                    f"Low confidence OCR result: {result.confidence}",
                    confidence=result.confidence,
                    text=result.text
                )
        except MemoryError:
            raise VisionError("Failed to allocate memory for image processing")
    """
    pass


class StateMachineError(PokemonAIError):
    """State machine errors.
    
    Raised when issues occur in the hierarchical state machine
    including invalid state transitions, undefined states, or
    state corruption.
    
    Common scenarios:
        - Invalid state transition attempted
        - Required state not found
        - State machine not initialized
        - Deadlock detected
        - State history corruption
        - Event handler missing
    
    Example:
        try:
            state_machine.transition(event)
        except InvalidTransitionError:
            raise StateMachineError(
                f"Invalid transition from {current_state} on event {event}",
                current_state=current_state.name,
                event=event.name,
                valid_events=current_state.valid_transitions()
            )
    """
    pass


class CombatError(PokemonAIError):
    """Combat system errors.
    
    Raised when issues occur during battle calculations, move
    selection, damage calculations, or combat state management.
    
    Common scenarios:
        - Invalid move selection
        - Damage calculation overflow
        - Turn order conflict
        - Status effect invalid
        - HP calculation error
        - Move compatibility issue
        - Weather condition invalid
    
    Example:
        try:
            damage = calculate_damage(attacker, defender, move)
            if damage > MAX_DAMAGE_VALUE:
                raise CombatError(
                    f"Damage calculation overflow: {damage}",
                    damage=damage,
                    max_expected=MAX_DAMAGE_VALUE
                )
        except ValueError as e:
            raise CombatError(f"Invalid combat parameter: {e}")
    """
    pass


class MemoryError(PokemonAIError):
    """Memory system errors.
    
    Raised when issues occur during memory reading, writing, or
    memory address validation in the game emulator.
    
    Common scenarios:
        - Invalid memory address
        - Memory read/write failure
        - Cheat code injection error
        - Memory bank switch error
        - RAM/ROM access violation
        - Checksum mismatch in memory
    
    Example:
        try:
            value = memory.read(address, size)
            if not validate_checksum(value, address):
                raise MemoryError(
                    f"Memory checksum mismatch at address 0x{address:04X}",
                    address=address,
                    expected_checksum=expected,
                    actual_checksum=actual
                )
        except AddressOutOfRangeError:
            raise MemoryError(f"Invalid memory address: 0x{address:04X}")
    """
    pass


class NavigationError(PokemonAIError):
    """Navigation errors.
    
    Raised when issues occur during world navigation including
    pathfinding, movement execution, or location validation.
    
    Common scenarios:
        - Pathfinding algorithm fails
        - Destination unreachable
        - Movement blocked
        - Map data corrupted
        - Coordinate out of bounds
        - Collision detection error
        - Route calculation timeout
    
    Example:
        try:
            path = find_path(current_pos, target_pos)
            if not path:
                raise NavigationError(
                    f"No valid path to destination",
                    current=current_pos,
                    target=target_pos
                )
        except PathfindingTimeout:
            raise NavigationError("Pathfinding calculation timed out")
    """
    pass


class DialogueError(PokemonAIError):
    """Dialogue system errors.
    
    Raised when issues occur during NPC dialogue, menu interactions,
    or text display operations.
    
    Common scenarios:
        - Dialogue tree invalid
        - Menu option out of range
        - Text extraction fails
        - Response parsing error
        - Dialogue state corrupted
        - Branch not found
        - Variable substitution fails
    
    Example:
        try:
            response = select_dialogue_option(dialogue_tree, user_choice)
            if response is None:
                raise DialogueError(
                    f"Invalid dialogue option: {user_choice}",
                    dialogue_id=dialogue_tree.id,
                    valid_options=dialogue_tree.options
                )
        except KeyError as e:
            raise DialogueError(f"Missing dialogue branch: {e}")
    """
    pass


class EntityError(PokemonAIError):
    """Entity management errors.
    
    Raised when issues occur during Pokémon, item, or NPC entity
    operations including creation, validation, or attribute access.
    
    Common scenarios:
        - Invalid entity attributes
        - Entity not found
        - Entity type mismatch
        - Evolution invalid
        - Item compatibility error
        - Inventory capacity exceeded
        - Stat calculation error
    
    Example:
        try:
            pokemon = get_pokemon(pokemon_id)
            if not pokemon.is_valid():
                raise EntityError(
                    f"Invalid Pokémon entity: missing required attributes",
                    entity_type="pokemon",
                    entity_id=pokemon_id,
                    missing_attributes=pokemon.missing_attrs()
                )
        except EntityNotFoundError:
            raise EntityError(f"Entity not found: {pokemon_id}")
    """
    pass


class ConfigurationError(PokemonAIError):
    """Configuration and CLI errors.
    
    Raised when issues occur during configuration loading, validation,
    CLI argument parsing, or settings management.
    
    Common scenarios:
        - Config file not found
        - Invalid config format
        - Missing required setting
        - Setting value invalid
        - CLI argument parsing error
        - Environment variable missing
        - Secret not found
    
    Example:
        try:
            config = load_config(config_path)
            validate_config(config)
        except ValueError as e:
            raise ConfigurationError(
                f"Invalid configuration value: {e}",
                config_path=config_path,
                setting=invalid_setting
            )
        except argparse.ArgumentError as e:
            raise ConfigurationError(f"CLI argument error: {e}")
    """
    pass