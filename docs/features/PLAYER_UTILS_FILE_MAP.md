# Player Utils File Map
Source file: `static\js\modules\player-utils.js`  Total lines: **2474**

Each segment is documented below. `hash` is SHA-1 of code with all whitespace removed, used to verify integrity after refactor.

| # | Type | Function | Params | Lines | Hash |
|---|------|----------|--------|-------|------|
| 1 | other_code |  |  | 1-11 | `ea7997d795a32d9e35d39ea90beb1da4ea2323d2` |
| 2 | function | shuffle | array | 12-17 | `b36989dce0b922b9b783100b20a1185435ed7653` |
| 3 | other_code |  |  | 18-25 | `cba6725abf6332641c44ef41b789d15db89d815c` |
| 4 | function | smartShuffle | list | 26-48 | `2b40a569a97fec065496650d3e71d84c74373687` |
| 5 | other_code |  |  | 49-56 | `a315ace8cf7856932d2c73ad9809e603e364ed17` |
| 6 | function | detectChannelGroup | track | 57-105 | `4b79bff47a6d25b624947714a6c57981142872b3` |
| 7 | other_code |  |  | 106-116 | `079911bb4bb034610ec823941239674c8291772c` |
| 8 | function | smartChannelShuffle | tracks | 117-197 | `6121b5b5f8f1429abef7ed30c40a4ba908cad154` |
| 9 | other_code |  |  | 198-204 | `ca42b98899232fcd17a775a3aebacd9d23e6de3a` |
| 10 | function | getGroupPlaybackInfo | tracks | 205-229 | `642b6ba6fffa0b59efa70a3eba3bfb6edb31b72e` |
| 11 | other_code |  |  | 230-239 | `3f1a6c8b4756d357c8facea5ad844127af0e4be3` |
| 12 | function | orderByPublishDate | tracks, schema = 'regular' | 240-296 | `9f6816b0bd83e57fd985354a59c48a9687f58014` |
| 13 | other_code |  |  | 297-304 | `d2651287df47560ba19c44ac365ee7d4e57d3f5f` |
| 14 | function | formatTime | s | 305-310 | `c0c493fa3141c2e907fcb78682a627fc24903557` |
| 15 | other_code |  |  | 311-318 | `94b79fee55e1edef2e5ad2a60814b7dd9ad33427` |
| 16 | function | updateSpeedDisplay | currentSpeedIndex, speedOptions, speedLabel, cSpeed | 319-327 | `3321c0a05cbb012e176e985ad830c988fca9b789` |
| 17 | other_code |  |  | 328-333 | `f0c3753bc93c3364d1b76cd3a371f0711ee51c7b` |
| 18 | function | showNotification | message, type = 'info' | 334-381 | `2657545b4086b903e204bbc0386cdaa4c07b4f81` |
| 19 | other_code |  |  | 382-391 | `7795fcaa208f4591f0f11b98f1084ec7cf41ed17` |
| 20 | function | handleVolumeWheel | e, cVol, media, updateMuteIcon, saveVolumeToDatabase, volumeState | 392-432 | `de2071e96f64b1c5a0a096d64912d7209004c9f3` |
| 21 | other_code |  |  | 433-440 | `ad0ecc8a9a3c82dc92baa38035c0f5589195a89b` |
| 22 | function | stopTick | tickTimer | 441-447 | `1fcfacfda8d7edf74ed612930ab8a4d5cb0969e1` |
| 23 | other_code |  |  | 448-452 | `3381ac881194708b468755bfebef9e52c52a64e5` |
| 24 | function | stopPlayback | media | 453-456 | `0c4c0af2e814d93ee6eece26bc4b8f0cc72c655f` |
| 25 | other_code |  |  | 457-462 | `9f8ebb64508188f04f340c798c250351394d6ff1` |
| 26 | function | playIndex | idx, loadTrack | 463-465 | `372b6ba10c513ee1933acbfbfd9b5816d84e9769` |
| 27 | other_code |  |  | 466-471 | `29c2fcb6b415df241bdc56b69b1c40297beaab1b` |
| 28 | function | updateMuteIcon | media, cMute | 472-478 | `f3e94ecba501dc09282d9b08df6cb6c06d267983` |
| 29 | other_code |  |  | 479-490 | `058e7d1adc23a00f83f778a7feeefe910337ad25` |
| 30 | function | nextTrack | currentIndex, queue, reportEvent, playIndex, sendStreamEvent, media | 491-498 | `7ef9541d7d1a8fe3f695290527c63ec6de8af1b2` |
| 31 | other_code |  |  | 499-508 | `be674e5534bcad7dea0760c08612677e1fa71a81` |
| 32 | function | prevTrack | currentIndex, queue, reportEvent, playIndex, sendStreamEvent, media | 509-515 | `23c226df293e34387e3845fc326ed6da7a013497` |
| 33 | other_code |  |  | 516-523 | `1b3ceeb5b9117a5aeb4e1d0d36cfa194d21ae98a` |
| 34 | function | sendStreamEvent | payload, streamIdLeader | 524-531 | `96f11d05eec7208a630dcd38b057b3171df45860` |
| 35 | other_code |  |  | 532-541 | `0bfbef1a435889e798f894272e519f884a1222f2` |
| 36 | function | startTick | tickTimer, streamIdLeader, sendStreamEventFn, currentIndex, media | 542-551 | `78bf165a283e0fafc4205f243a324c47a5c38744` |
| 37 | other_code |  |  | 552-560 | `85b05e854f42f97727a30760b9d1209b0ed549bb` |
| 38 | function | reportEvent | videoId, event, position = null | 561-572 | `cd554bc05eb11e0ebe50a0280b699d2893118e5d` |
| 39 | other_code |  |  | 573-579 | `8a117ee13801a5327827c37f9f767f6549e7f763` |
| 40 | function | triggerAutoDeleteCheck | track, detectChannelGroupFn, media | 580-604 | `c6851d67d1591091832c15a2591d46add7781c11` |
| 41 | other_code |  |  | 605-614 | `d2776ec8753d345203e504c15ee8d4ed5a3289c5` |
| 42 | function | recordSeekEvent | video_id, seek_from, seek_to, source | 615-639 | `a79ae7181f21b0a79053f441a291347807954d1f` |
| 43 | other_code |  |  | 640-651 | `93b95c845e5ef4e43ed90a779d070a5bfaf4da84` |
| 44 | function | performKeyboardSeek | offsetSeconds, context | 652-665 | `b000db0ce59d6dcf639f68fa60a2a767e5f55c81` |
| 45 | other_code |  |  | 666-669 | `0eb08c2b42a150b3e7287af02f5662cad2e8f825` |
| 46 | function | syncLikeButtonsWithRemote |  | 670-698 | `a563ed3b6007a40c10a07a74031a8dae0dab79bf` |
| 47 | other_code |  |  | 699-705 | `62e8ed1833f75202f543604daed855063215ccdb` |
| 48 | function | syncLikesAfterAction | video_id, action, syncRemoteState | 706-713 | `59a413cf44da7df8951e5e7d992f8370e9deece5` |
| 49 | other_code |  |  | 714-721 | `b1c9bbeab40aebf9cf004f7864670e7f5593b9aa` |
| 50 | function | setupLikeSyncHandlers | context | 722-763 | `fd35623f86cbfb34efd5437c5e439a118cd74b4b` |
| 51 | other_code |  |  | 764-773 | `9518e626ca1f9415d7547674c57f55bd129f0580` |
| 52 | function | saveVolumeToDatabase | volume, context | 774-803 | `d44120006d0111e62b6d429c9b6d4bf524783227` |
| 53 | other_code |  |  | 804-811 | `84554662b41ba4bd82c86ddce752dd61c865324b` |
| 54 | function | loadSavedVolume | media, cVol, state, updateMuteIcon | 812-837 | `150c8478a585a9aea18a89c227f7cf1baee3f18d` |
| 55 | other_code |  |  | 838-847 | `4df89b1e242497658430ba9768d48c18d4cec7cb` |
| 56 | function | togglePlayback | context | 848-859 | `46f07eddda6668d189b0fe7c6ee5057c699422a9` |
| 57 | other_code |  |  | 860-869 | `f0df28bced1d3c11ec43aef1e7cd68784ddaa02c` |
| 58 | function | showFsControls | context | 870-891 | `6b0d27a5ca2b7ee875532d8286b36675bbe91c27` |
| 59 | other_code |  |  | 892-897 | `f91f821c326a7102282d6194f09a95fbc4b8c12e` |
| 60 | function | updateFsVisibility | context | 898-913 | `3ec58ec9a69dcf5ebc5683c078cdd4af65365c70` |
| 61 | other_code |  |  | 914-919 | `c11b8af92f091931e633c06d39a0a2eaa6adc1ac` |
| 62 | function | syncRemoteState | playerType = 'regular', context | 920-967 | `2872b04fb21a0c79d3851c8cbf22a2d025968f9f` |
| 63 | other_code |  |  | 968-977 | `5a26e72500797318a069c15c86d5697d71c72652` |
| 64 | function | formatFileSize | bytes | 978-987 | `65c7ac39cd8bf34ca6accde7aba3d349975d2eb0` |
| 65 | other_code |  |  | 988-993 | `ed53690ccde6e0276a4222b51d3656980b27f52c` |
| 66 | function | createTrackTooltipHTML | track | 994-1104 | `caed9d5bb6049f6d40f21e14c90adbdd1c1905a9` |
| 67 | other_code |  |  | 1105-1110 | `17fe790c526feebda503b2fdf5b9d80f1648619f` |
| 68 | function | setupGlobalTooltip | listElem | 1111-1175 | `9b4b834a4ded92201d6eac07a6f766197b9cfc23` |
| 69 | other_code |  |  | 1176-1181 | `2e5ad0f84b86fd84953ba8de8fae218ec7ceecbe` |
| 70 | function | pollRemoteCommands | executeRemoteCommand, verbose = false | 1182-1217 | `1fc2f0a3934b07f3c8de47b392238dfcbf295615` |
| 71 | other_code |  |  | 1218-1224 | `35b7d66126cd3fa015816fbeef6b36935d3f98e1` |
| 72 | function | cyclePlaybackSpeed | context, savePlaylistSpeed = null, playerType = 'regular' | 1225-1262 | `0c8d9598a8a47fe8a5f2c56ea18eed2e4b210990` |
| 73 | other_code |  |  | 1263-1273 | `8a2dca8d8e8a5239a78bf4143ef8ed8b0441c206` |
| 74 | function | executeRemoteCommand | command, context, playerType = 'regular' | 1274-1431 | `55d0faa4148b84a8d6c09154452e8ab9025bd485` |
| 75 | other_code |  |  | 1432-1442 | `cce2445820acbad8a08b1571b8d45692fbf48794` |
| 76 | function | deleteTrack | track, trackIndex, context | 1443-1576 | `c134ef220547a931886b747ecaa561334bae63d9` |
| 77 | other_code |  |  | 1577-1589 | `e272a54aa8218ceb3da8076d7bd6a56b60c92a71` |
| 78 | function | initializeGoogleCastIntegration | context | 1590-1707 | `acdf6b1ec6f5a140315b51ff78638e5e83dc1da0` |
| 79 | other_code |  |  | 1708-1713 | `0e745c6b7e8c0d7517b848be5fc3a88dce111d5e` |
| 80 | function | castLoad | track, castState | 1714-1774 | `aa5170e1db5fff533eedff30bf65b91625feee11` |
| 81 | other_code |  |  | 1775-1786 | `187b578baadba005f278563f0a56f36e008aa1bf` |
| 82 | function | loadTrack | idx, autoplay = false, context | 1787-1827 | `98276d13eddc507dfa0c76b02c10951be3f298c7` |
| 83 | other_code |  |  | 1828-1842 | `1372ab6dffc619e742c672f4d9ea5946a7a3a39c` |
| 84 | function | setupMediaEndedHandler | media, context | 1843-1867 | `fa8725bc5fadef883fa4cfa24f86b123714af758` |
| 85 | other_code |  |  | 1868-1877 | `9c64902b0f961b8e1a9620a1499c639a092aea90` |
| 86 | function | setupMediaPlayPauseHandlers | media, context | 1878-1898 | `a67f9d68857dcf37be18086d6b807bab721a7f98` |
| 87 | other_code |  |  | 1899-1907 | `7205df438185d0478ea726870e286ec20cd79d98` |
| 88 | function | setupMediaTimeUpdateHandler | media, context | 1908-1914 | `e6832ebf7649f23e020d4188bef5c7c43b784e42` |
| 89 | other_code |  |  | 1915-1924 | `e4288c5e53ab79bdf95a001397ae3e814e0503f6` |
| 90 | function | setupMediaSeekedHandler | media, context | 1925-1943 | `2e1fa03a282e851e1fc3ee07c7dba6260a0c2311` |
| 91 | other_code |  |  | 1944-1952 | `71dde5bb09c58562000134c37a8e945f80cfd012` |
| 92 | function | setupKeyboardHandler | context | 1953-1989 | `0fbfc70cbdfec2ed7b5e2c6b8264d261cee6b0e2` |
| 93 | other_code |  |  | 1990-1999 | `035d272a565998f8b47a65a87cbe8b10087fa904` |
| 94 | function | setupProgressClickHandler | progressContainer, media, context | 2000-2020 | `5ee3fae5ea95617067aa3b00be6d51798887be65` |
| 95 | other_code |  |  | 2021-2028 | `6f999d5ac1fe1d14a21414b066ac23157b3676c0` |
| 96 | function | setupMediaSessionAPI | context | 2029-2037 | `13614b9040acd33b5150f35288c0be30f8ff3a45` |
| 97 | other_code |  |  | 2038-2043 | `9239db357e8d1d107d8f2b1db7c17a81b24a7259` |
| 98 | function | setupPlaylistToggleHandler | toggleListBtn, playlistPanel | 2044-2057 | `ef9a42ca5439fca1811a5f06c73eac07f9fa8e51` |
| 99 | other_code |  |  | 2058-2079 | `92d7f65280bad617ba02a4477322b1ad8ce512b6` |
| 100 | function | executeDeleteWithoutConfirmation | context, playerType = 'regular' | 2080-2188 | `40d839cef34fff2c6b335dd7c70472a063430a35` |
| 101 | blank_or_comments |  |  | 2189-2189 | `` |
| 102 | function | setupDeleteCurrentHandler | deleteCurrentBtn, context, playerType = 'regular' | 2190-2217 | `372cac1fe244dcea30d12d0e8c12e12187a570d7` |
| 103 | other_code |  |  | 2218-2229 | `3fd75142aa236d4ad1a2d7ca7163788d9fc9243a` |
| 104 | function | setupLikeDislikeHandlers | cLike, cDislike, context | 2230-2255 | `193071ec15097bd898918449e89dd761e2f25971` |
| 105 | other_code |  |  | 2256-2263 | `1486fd060e6fc40cd9ab56c80b049530eec19888` |
| 106 | function | setupYouTubeHandler | cYoutube, context | 2264-2278 | `80181c8270d6d3e57e9fe5b8166f61da30e47ac4` |
| 107 | other_code |  |  | 2279-2285 | `7181e31d911a95d1fe8ae71ffa65fba0cff657a7` |
| 108 | function | setupFullscreenHandlers | fullBtn, cFull, wrapper | 2286-2302 | `eeef4969eee4d9df6628ef0e3873974386a68ec2` |
| 109 | other_code |  |  | 2303-2312 | `5cbf49d0b391c0b59b4ef72047fa518b3b070d96` |
| 110 | function | setupSimpleControlHandlers | cPrev, cNext, media, prevTrack, nextTrack, togglePlayback | 2313-2326 | `2287bf84fdc45ed1cca8225b270360f4eb4190bc` |
| 111 | other_code |  |  | 2327-2338 | `2724024153c9858c1e9ebb1f7944d14758d72977` |
| 112 | function | setupStreamHandler | streamBtn, context | 2339-2392 | `1250433c4f528249fbc68b04ea08cdd96f7acd87` |
| 113 | other_code |  |  | 2393-2397 | `1b5975fe63b8747c4fcc46a551d426459be83a5f` |
| 114 | function | setupBeforeUnloadHandler | stopTick | 2398-2400 | `e78d51debdc3bbf946d468300e671eece9a474a5` |
| 115 | other_code |  |  | 2401-2408 | `4831fa84c3f4f1ef1023255e091dce267c02f05e` |
| 116 | function | setupAutoPlayInitialization | queue, playIndex, renderList, syncRemoteState | 2409-2418 | `6178ac0f9779cd1908b8bbd2d215d728c5a5d032` |
| 117 | other_code |  |  | 2419-2425 | `efd9ff952de1296cbda85a1f33e160e439b8e252` |
| 118 | function | setupRemoteControlOverrides | playIndex, togglePlayback, syncRemoteState | 2426-2439 | `35d290175f2c868d7ea0da921edf8e91884b3a86` |
| 119 | other_code |  |  | 2440-2447 | `625a1cefdf5fe2d76788c74195d470f690318f36` |
| 120 | function | setupRemoteControlInitialization | media, syncRemoteState, pollRemoteCommands, context | 2448-2474 | `474564ccea28e165c7dc4e9345fb955eff5ee49a` |
