"""
List management example for the Affinity SDK.

This example demonstrates:
- Working with lists and list entries
- Adding entities to lists
- Updating field values
- Using saved views
"""

import os

from affinity import Affinity
from affinity.types import CompanyId, FieldType, ListId, ListType


def main() -> None:
    api_key = os.environ.get("AFFINITY_API_KEY")
    if not api_key:
        print("Please set AFFINITY_API_KEY environment variable")
        return

    with Affinity(api_key=api_key) as client:
        # Get all lists and find an opportunity pipeline
        print("Finding opportunity lists...")
        opportunity_list: ListId | None = None

        for lst in client.lists.all():
            print(f"  {lst.name} (type: {lst.type.name})")
            if lst.type == ListType.OPPORTUNITY and opportunity_list is None:
                opportunity_list = lst.id

        if opportunity_list is None:
            print("\nNo opportunity list found. Creating one would require specific permissions.")
            return

        print(f"\nUsing list ID: {opportunity_list}")
        print()

        # Get list details with field metadata
        lst = client.lists.get(opportunity_list)
        print(f"List: {lst.name}")
        print(f"Fields: {len(lst.fields or [])} fields defined")

        for field in (lst.fields or [])[:5]:
            print(f"  - {field.name} ({field.value_type.name})")
        print()

        # Get entries service for this list
        entries = client.lists.entries(opportunity_list)

        # List entries with field values
        print("List entries (first 5):")
        print("-" * 50)
        result = entries.list(
            field_types=[FieldType.LIST],
            limit=5,
        )

        for entry in result.data:
            entity_name = "Unknown"
            if hasattr(entry.entity, "name"):
                entity_name = entry.entity.name  # type: ignore
            elif hasattr(entry.entity, "first_name"):
                entity_name = f"{entry.entity.first_name} {entry.entity.last_name}"  # type: ignore

            print(f"  {entity_name}")
            if entry.fields.requested and entry.fields.data:
                for field_id, value in list(entry.fields.data.items())[:3]:
                    print(f"    {field_id}: {value}")
        print()

        # Get saved views
        print("Saved views:")
        print("-" * 50)
        views = client.lists.get_saved_views(opportunity_list)
        for view in views.data:
            print(f"  {view.name} (type: {view.type})")
            if view.field_ids:
                print(f"    Field IDs: {len(view.field_ids)}")
        print()

        # Example: Getting entries from a saved view
        if views.data:
            view = views.data[0]
            print(f"Entries from '{view.name}' view:")
            view_entries = entries.from_saved_view(view.id, limit=3)
            for entry in view_entries.data:
                if hasattr(entry.entity, "name"):
                    print(f"  - {entry.entity.name}")  # type: ignore


def example_add_company_to_list(
    client: Affinity,
    list_id: ListId,
    company_id: CompanyId,
) -> None:
    """Example of adding a company to a list and updating field values."""
    entries = client.lists.entries(list_id)

    # Add the company to the list
    entry = entries.add_company(company_id)
    print(f"Added company to list, entry ID: {entry.id}")

    # Update a field value (requires knowing the field ID)
    # field_id = FieldId(12345)  # Replace with actual field ID
    # entries.update_field_value(entry.id, field_id, "In Progress")

    # Batch update multiple fields
    # entries.batch_update_fields(
    #     entry.id,
    #     {
    #         FieldId(101): "Negotiation",
    #         FieldId(102): 50000,
    #     }
    # )


if __name__ == "__main__":
    main()
