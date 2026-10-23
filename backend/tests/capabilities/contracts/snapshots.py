"""Reviewed executable contracts. Update deliberately with action fixtures."""

FINGERPRINTS = {
    (
        "add_rss_feed",
        "v1",
    ): "49cdf2626cdc2020204468f8ea9b8cf97918af2d2e1e8e1ffb61a5586aa050c1",
    (
        "analyse_taste",
        "v1",
    ): "418a6e08d5637c5292849c8cbdce6082491e71e6afe739c3b498b65211873751",
    (
        "batch_upsert_collections",
        "v1",
    ): "de54b198c0c18b090c600591d727cb888f9e18558f9cabf052855c175c77b1af",
    (
        "bulk_upsert_schedules",
        "v1",
    ): "17fde09da344a9e763a9594eafcaa58183f739c234f8323f61d8a344c55fc2d5",
    (
        "create_collection",
        "v1",
    ): "73c3ef232fb1ede718b0c29a6388581ac0c96248c711e390bbc7ec301014b117",
    (
        "create_schedule",
        "v1",
    ): "eda1cc394246a502815000cd4fbc97da19de2ea82ffbd7c7b0283008a9657650",
    (
        "delete_collection",
        "v1",
    ): "7db3edc57fcda137c3fd39b970a52f730568b7748f89601d0d88e81cb846c659",
    (
        "delete_schedule",
        "v1",
    ): "3857044ce5dcadf671f7e0a1514ba539dce91b23241b813c739b380366b5790a",
    (
        "fetch_audience_reviews",
        "v1",
    ): "0d2147d3efd1d4ce759296e6a1d6bf30cb7bcebc121ff98e44e4889121cc2505",
    (
        "generate_user_profile_tool",
        "v1",
    ): "02a17d4acd8db3e08dac1d7b4eaae22760fad31ae70a3a0875089573d3431bc4",
    (
        "get_anime_cast",
        "v1",
    ): "05340e56e1ce6244c0db9e4b97855a81bc06fdc7b443ec54e5e5c939671be3c7",
    (
        "get_anime_info",
        "v1",
    ): "4aaea360ace6e2540648c859067916a9b86fad596aebf5e9b350c0199e52e846",
    (
        "get_anime_info_batch",
        "v1",
    ): "93eb61fdff5daeb0f8c48bf3bc6f681407d6549ede5ac8a426f9ea216b5ebd07",
    (
        "get_anime_staff",
        "v1",
    ): "70da7c38d5da64f9dca99a301ad281a9175e0a90685286c3502863dab047a3cd",
    (
        "get_bangumi_calendar",
        "v1",
    ): "828043bbb1786cc47c4bee2818e0786d9372b2cb3b2ea394f33b0ecd4174a579",
    (
        "get_bangumi_user_info",
        "v1",
    ): "82d66599b84dcf9eadcb90a76a298959519c2808226bf70bc2202b55b04aeba2",
    (
        "get_collection",
        "v1",
    ): "e63d7d04bb111a9ad1cbb8694e38214eadd85e1fdc02acbd5702735f136e08a3",
    (
        "get_collection_statistics",
        "v1",
    ): "d585e105f405b8728359c1a11f1a80ad9f1c827cbdf36238613c5a7ce85466d1",
    (
        "get_current_time",
        "v1",
    ): "e28458c616d4a4d01b94a8a4db2156cc60abc1bfd403c7ae834871e0d7308deb",
    (
        "get_subject",
        "v1",
    ): "e29cf22a2b11bc02330a69be2a67972a95a058a6715efb1b7ee2e5dfcd638e4a",
    (
        "get_subject_air_time",
        "v1",
    ): "78688b3da3ba87caf2b286ec1bb9f000261b3a2e93b12bdbd46dc3e57dfaa2fb",
    (
        "get_user_stats",
        "v1",
    ): "43ec963d72ceefba947efe7bf435598f8ed9009ff28539d0ab6ddb8ecec0554e",
    (
        "import_json_collections",
        "v1",
    ): "488a36a6a5ec47f62607a9236962583124b970a586b6d7c3aa7b646f95c22bda",
    (
        "library_status",
        "v1",
    ): "7abbf4a214578545a9a1f9be9c99564e419b277178f88d91f692f297b2049043",
    (
        "list_collections",
        "v1",
    ): "4be11cb68dd7a90ad86ed25a6aae77aa6a37f7444ac4dc329f98c371d0f74423",
    (
        "list_rss_feeds",
        "v1",
    ): "beb8b8fe1c058a03377a850c907d3080f01b6557ea8455f48f92c600f4f6c13e",
    (
        "list_rss_rules",
        "v1",
    ): "7069346b4713b8a47c34563e6e1026597f41fc4e74c0a157e6534e07ab8f06a0",
    (
        "list_schedules",
        "v1",
    ): "d4fe37596f21a45feb22df1ed5d83bc3f3a3d3fa2cdf9081a4af6f5454f2332f",
    (
        "list_schedules_by_day",
        "v1",
    ): "0da568d5f61cf27923e624495545fbb7d866e6523ece667eb979904686c33f76",
    (
        "list_unified_schedules",
        "v1",
    ): "bb2f0b379dca74964414c791a3b68e2ff363b823dd3348e1403c031bf6835cb7",
    (
        "remove_rss_feed",
        "v1",
    ): "bba549c62d0fcb03a3893d366382b2f91eedee2d248e1b23b6f6256ccea878e7",
    (
        "remove_rss_rule",
        "v1",
    ): "7ab6cf533b742527bfec8886189deb60e2e2a2154e260dfdbbd487e20bbfa505",
    (
        "search_anime_advanced",
        "v1",
    ): "896d6c34cf83c2eb99b84f671249b6ec2b6c56d8bd58c3c1f697d0e99b55442f",
    (
        "search_collections",
        "v1",
    ): "1e8246540e66fc0c791ff061a816e7c7dffb25d9a9b15da0dabecf822ec96b0d",
    (
        "search_local_subjects",
        "v1",
    ): "463ae0b93a55594fb55708f521c222b803c9ab2a89b3aa1364b92e7d66ad4a2b",
    (
        "search_mixed_subjects",
        "v1",
    ): "91ddc316a10e742e0de5b0a1f21480731ae39b30f785e287b2eb991631adf1f4",
    (
        "search_remote_subjects",
        "v1",
    ): "cde9f7fbb860860781d3ace9f5ef3b216450d3a8a9b3cb20a220c5c26d9a6220",
    (
        "set_rss_rule",
        "v1",
    ): "9a0eecd4ccf96b30bce6a0c7b9d62bd5a8a146dd5c48e5be88c076fc2e313636",
    (
        "sync_bangumi_collections",
        "v1",
    ): "b5af4e7d8ebe39f901061934d6c56d82511da00e8b0154f02204b4f09e8798d8",
    (
        "sync_bangumi_schedule",
        "v1",
    ): "01a48c36e8c3d673b7abea3c99739c6831dcde14847a99f03aae88ae0edb30bc",
    (
        "sync_douban_collections",
        "v1",
    ): "6ba32c63ec184a51fb10c19fc7b08838533287138198e1f89b421ca1e8a60145",
    (
        "update_collection",
        "v1",
    ): "c8c7c0614c4b135f8782bac962927fa192989009ff66b984fbb8d28670d6388f",
    (
        "update_schedule",
        "v1",
    ): "dcbc36ee7a712e9424a91244b527b5393a31e500d701a1da1250b0396452746e",
    (
        "upsert_collection",
        "v1",
    ): "e2c9d12fa6373c864aa4f035b5b3bb1611e9933bbcc10b8a06b0e4c9fc0dd141",
    (
        "upsert_rss_feed",
        "v1",
    ): "1864249f16ca9b51e156af6e174b3aab97ce1651ee0781c5c006cb6d9d26e1d6",
    (
        "upsert_schedule",
        "v1",
    ): "e31fbbb733ddd96c7a2b14f42b90a5942517d0c857109fd79ad3f1edd1753053",
}
