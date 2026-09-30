"""Add entities that become discoverable after platform setup."""


def setup_entity_discovery(
    config_entry,
    coordinator,
    async_add_entities,
    discover_entities,
) -> None:
    """Add each discovered entity once and listen for coordinator updates."""
    known_ids = set()

    def add_new_entities() -> None:
        additions = []
        addition_ids = set()
        for entity in discover_entities():
            unique_id = entity.unique_id
            if unique_id in known_ids or unique_id in addition_ids:
                continue
            additions.append(entity)
            addition_ids.add(unique_id)

        if additions:
            async_add_entities(additions, True)
            known_ids.update(addition_ids)

    add_new_entities()
    config_entry.async_on_unload(coordinator.async_add_listener(add_new_entities))
