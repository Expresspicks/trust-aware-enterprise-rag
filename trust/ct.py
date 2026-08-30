def calculate_contextual_trust(
    question,
    mode,
    sql_query=None,
    role_name=None,
    user_region=None,
):
    regions = ["VIC", "NSW", "QLD"]

    question_lower = question.lower()
    sql_lower = sql_query.lower() if sql_query else ""

    sensitive_words = [
        "password",
        "credentials",
        "all users",
        "delete",
        "drop",
        "truncate",
        "private",
        "confidential",
    ]

    # Default output
    result = {
        "ct_score": 50,
        "ct_reason": "Default contextual trust.",
        "hard_block": False,
        "block_message": None,
    }

    # Unknown role
    if role_name not in ["admin_manager", "manager", "sales_rep", "intern"]:
        result["ct_score"] = 0
        result["ct_reason"] = "Unknown user role. Context cannot be trusted."
        result["hard_block"] = True
        result["block_message"] = "Access denied. Unknown user role."
        return result

    # Sensitive or dangerous query
    if any(word in question_lower for word in sensitive_words):
        result["ct_score"] = 10
        result["ct_reason"] = "Sensitive or risky query detected."
        result["hard_block"] = False
        result["block_message"] = None
        return result

    # Admin manager: full enterprise access
    if role_name == "admin_manager":
        result["ct_score"] = 95
        result["ct_reason"] = (
            "Admin manager has full enterprise-level contextual access."
        )
        return result

    # Manager: high access
    if role_name == "manager":
        result["ct_score"] = 85
        result["ct_reason"] = "Manager has high business-level contextual access."
        return result

    # Intern: restricted access
    if role_name == "intern":
        result["ct_score"] = 40
        result["ct_reason"] = "Intern has limited contextual access."

        if mode in ["sql", "both"] and "finance" in sql_lower:
            result["ct_score"] = 20
            result["ct_reason"] = "Intern attempted to access finance data."
            result["hard_block"] = True
            result["block_message"] = (
                "Access denied. Interns cannot access finance data."
            )

        return result

    # Sales rep: regional access only
    if role_name == "sales_rep":
        result["ct_score"] = 75
        result["ct_reason"] = (
            f"Sales rep context is valid for assigned region: {user_region}."
        )
        
        
        user_region_lower = user_region.lower() if user_region else ""
        # Check if the question clearly mentions the user's own region
        own_region_requested = (
            user_region_lower in question_lower if user_region_lower else False
        )




        # Asking another region explicitly
        for region in regions:
            if region != user_region:
                if region.lower() in question_lower or region.lower() in sql_lower:
                    result["ct_score"] = 25
                    result["ct_reason"] = (
                        f"Sales rep requested data outside assigned region: {user_region}."
                    )
                    result["hard_block"] = True
                    result["block_message"] = (
                        f"Access denied. You can only access {user_region} data."
                    )
                    return result

        # Asking broad regional comparison
        broad_region_words = [
            "by region",
            "all region",
            "all regions",
            "each region",
            "every region",
            "region wise",
            "region-wise",
            "across regions",
            "compare regions",
            "compare region",
            "which region",
            "what region",
            "top region",
            "best region",
            "highest region",
            "lowest region",
            "region has the highest",
            "region has the lowest",
            "highest sales",
            "lowest sales",
            "highest total sales",
            "lowest total sales",
            "highest performing region",
            "lowest performing region",
        ]
# If the question asks for cross-region comparison and is not clearly restricted to user's own region
        if any(word in question_lower for word in broad_region_words):
            if not own_region_requested:
                result["ct_score"] = 35
                result["ct_reason"] = (
                    "Sales rep requested an implicit cross-region comparison."
                )
                result["hard_block"] = True
                result["block_message"] = (
                    f"Access denied. This question requires comparison across regions. "
                    f"You can only access {user_region} data."
                )
                return result

        

    return result
