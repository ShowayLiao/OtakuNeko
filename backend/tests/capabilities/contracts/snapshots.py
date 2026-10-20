"""Reviewed executable contracts. Update deliberately with action fixtures."""

FINGERPRINTS = {
    (
        "add_rss_feed",
        "v1",
    ): "8985fb7c64c5a43b486001071b417df64693cec9a343832e6ae12318dc24a120",
    (
        "analyse_taste",
        "v1",
    ): "74e732bf44631dc5d24cee050f2199bbab62a8e7bc3c6f405551f2263ce12422",
    (
        "batch_upsert_collections",
        "v1",
    ): "207c7540f2636b9c5644955d10effd2a2e05eda927f7cc6119f97cded426dcb5",
    (
        "bulk_upsert_schedules",
        "v1",
    ): "ed38810e6c214f1a33d0f0b38e202c8d5a89c03e8351c21d62a15b44a9dce1b4",
    (
        "create_collection",
        "v1",
    ): "12eef5d9c53668e4fd8190afac6b53d1e9d448f6636468076329066fad81fab8",
    (
        "create_schedule",
        "v1",
    ): "81da02a8d3661ccdd046714f120b1ec082b26a9c4514907743266896b8568bda",
    (
        "delete_collection",
        "v1",
    ): "7ad69756f2863fc606145769c3ff3f1ef85d417c2a32bdd4762556e94d32941f",
    (
        "delete_schedule",
        "v1",
    ): "da9da42c6d4945ee7f68b2c8395a5588531213fb792fe4a2f60da25d1b381646",
    (
        "fetch_audience_reviews",
        "v1",
    ): "0d2147d3efd1d4ce759296e6a1d6bf30cb7bcebc121ff98e44e4889121cc2505",
    (
        "generate_user_profile_tool",
        "v1",
    ): "f41e02b654c2d486cc23b2957618714b846747f7c82924553531b9ef1553a72f",
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
    ): "11d67a8e44d085c621e32456308d738113cad41918434079f49ee10d9085a1c7",
    (
        "get_collection_statistics",
        "v1",
    ): "752e74d66f2278a2cef8d9e4891988b786d4aabf5a6aee63f163585fce5115b8",
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
    ): "7a20675cf807d7072de223595a04457c80599aca842d587b7284741e445bccd0",
    (
        "import_json_collections",
        "v1",
    ): "efa72626cbaf7087f71d88b12b8f170fa486a62f0108ebb05b93f5e660850aa8",
    (
        "library_status",
        "v1",
    ): "0791395e14a1d2f4ee74e69a054f906b4870ef5312a369dacf177e1a138ff099",
    (
        "list_collections",
        "v1",
    ): "67f13d41ffc3b3cc142274efd6fc73a77f3936494e701d7fc2d7cf1bd379092f",
    (
        "list_rss_feeds",
        "v1",
    ): "cb40629d27f52dffe23ad8bdb9196c5cb04933dc8eba4df39f31ab20bb1756ad",
    (
        "list_rss_rules",
        "v1",
    ): "73eccd57349b06bddc32360f900488ce5e8e5d0df2c3c76912f9a7892082c717",
    (
        "list_schedules",
        "v1",
    ): "6c137ab0440c362224bbeacec2f7e5436ea7e9752f123c186a4e89c9e1feea56",
    (
        "list_schedules_by_day",
        "v1",
    ): "a90e50ac531d22d56826b808c90164c6d4c4c27507d2dd0dc151ecaf71352cf6",
    (
        "list_unified_schedules",
        "v1",
    ): "f7aaadad159cc777563319e57978bf7132769ab17d0d87e3ea89146c3c01f492",
    (
        "remove_rss_feed",
        "v1",
    ): "b85377bd87717bb05d96d02471ad02421d8c2ec32a4dd7e437a1e10f70e4513c",
    (
        "remove_rss_rule",
        "v1",
    ): "79ad97e220840e6d98b92fe96ff2c7fb7ad4ea088674fa00a4d476c5975c5a8f",
    (
        "search_anime_advanced",
        "v1",
    ): "896d6c34cf83c2eb99b84f671249b6ec2b6c56d8bd58c3c1f697d0e99b55442f",
    (
        "search_collections",
        "v1",
    ): "09d5c189c8606f1086d627584bb03b4ef05998fbe6f47446560c5384d119fea1",
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
    ): "907b77b51b82f68f3644533743f8d094df22526b569332703c8192273b07a934",
    (
        "sync_bangumi_collections",
        "v1",
    ): "71472082e101d42e5a1ed6f7abc5878fa141349e0da344beca332a790a912d30",
    (
        "sync_bangumi_schedule",
        "v1",
    ): "3943bd6c7d2d4bb7c51c7fbe1d0e9f1389770419fab09a5f08921b211795dc4e",
    (
        "sync_douban_collections",
        "v1",
    ): "99b5a8351f7fed88dbdb76a3086d971d5491e0c02f198d43576c64d97d524266",
    (
        "update_collection",
        "v1",
    ): "2fa025447dc2814f0e22d96234d3aeb57dc7ec4ee19244162e4e24b14311d9ea",
    (
        "update_schedule",
        "v1",
    ): "50c42b485fad0d6dba2d9cbeba72ee7091f93e9fff7210bdbb7a83ea10f405f3",
    (
        "upsert_collection",
        "v1",
    ): "e18d7d01ed4f85c705fcfacca6f26791433141f249b477b66903c016144f8f61",
    (
        "upsert_rss_feed",
        "v1",
    ): "0cc2df8dc85fbc28cc4f903d14bc38c24dee575dda8d47de4760a0c9bca6605c",
    (
        "upsert_schedule",
        "v1",
    ): "b711bb999e49cc72facf823576466e68b5d28f075e18e0ac447db5fb854dd23b",
}
