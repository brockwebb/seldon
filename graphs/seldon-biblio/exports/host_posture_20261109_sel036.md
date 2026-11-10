# Host posture: seldon_biblio 20261109_sel036 (DN-055 R-243)

| host | posture | entries by posture | last observed | evidence | marked for a human |
|---|---|---|---|---|---|
| dl.acm.org | refused | refused 4 | 2026-11-09T23:34:57.008026+00:00 | HTTP 403 Forbidden at https://dl.acm.org/doi/pdf/10.1145/3768620; robots.txt HTTP 200 -> successful (RFC 9309 2.3.1.1) | erman1980hearsay, kahn1962topological, kelley1959critical, xiang2025splite |
| hdl.handle.net | refused | refused 1 | 2026-11-09T23:33:54.379126+00:00 | HTTP 403 Forbidden at http://hdl.handle.net/10393/41734; robots.txt HTTP 403 -> unavailable (RFC 9309 2.3.1.3), edge refused | rethlefsen2021prismas |
| pqdtopen.proquest.com | refused | refused 1 | 2026-11-09T23:34:55.070224+00:00 | HTTP 403 Forbidden at http://pqdtopen.proquest.com/#viewpdf?dispub=10139524; robots.txt HTTP 403 -> unavailable (RFC 9309 2.3.1.3), edge refused | pershina2014graph |
| www.gbv.de | refused | refused 1 | 2026-11-09T23:26:27.873516+00:00 | HTTP 403 Forbidden at http://www.gbv.de/dms/ilmenau/toc/673088804.PDF; robots.txt HTTP 403 -> unavailable (RFC 9309 2.3.1.3), edge refused | clelandhuang2012traceability |
| content.iospress.com | unreachable | unreachable 1 | 2026-11-09T23:29:08.498218+00:00 | not requested: https://content.iospress.com:443/download/information-services-and-use/isu613?id=information-services-and-use%2Fisu613; robots.txt ProxyError: HTTPSConnectionPool(host='content.iospress.com', port=443): Max retries exceeded with url: /robots.txt (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden'))) -> unreachable (RFC 9309 2.3.1.4) |  |
| content.scirp.org | unreachable | unreachable 1 | 2026-11-09T23:27:08.774392+00:00 | not requested: https://content.scirp.org/pdf/jsea_2014032713545074.pdf; robots.txt ProxyError: HTTPSConnectionPool(host='content.scirp.org', port=443): Max retries exceeded with url: /robots.txt (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden'))) -> unreachable (RFC 9309 2.3.1.4) |  |
| discovery.ucl.ac.uk | unreachable | unreachable 1 | 2026-11-09T23:26:25.253344+00:00 | not requested: https://discovery.ucl.ac.uk/749/1/2.2_rtprob.pdf; robots.txt ProxyError: HTTPSConnectionPool(host='discovery.ucl.ac.uk', port=443): Max retries exceeded with url: /robots.txt (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden'))) -> unreachable (RFC 9309 2.3.1.4) |  |
| jbiomedsem.biomedcentral.com | unreachable | unreachable 1 | 2026-11-09T23:29:10.096411+00:00 | not requested: https://jbiomedsem.biomedcentral.com/track/pdf/10.1186/2041-1480-1-S1-S6; robots.txt ProxyError: HTTPSConnectionPool(host='jbiomedsem.biomedcentral.com', port=443): Max retries exceeded with url: /robots.txt (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden'))) -> unreachable (RFC 9309 2.3.1.4) |  |
| publikationen.bibliothek.kit.edu | unreachable | unreachable 1 | 2026-11-09T23:29:32.121554+00:00 | not requested: https://publikationen.bibliothek.kit.edu/1000178348/156555617; robots.txt ProxyError: HTTPSConnectionPool(host='publikationen.bibliothek.kit.edu', port=443): Max retries exceeded with url: /robots.txt (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden'))) -> unreachable (RFC 9309 2.3.1.4) |  |
| www.jstage.jst.go.jp | unreachable | unreachable 1 | 2026-11-09T23:28:20.500574+00:00 | not requested: https://www.jstage.jst.go.jp/article/arepj1962/41/0/41_27/_pdf; robots.txt ProxyError: HTTPSConnectionPool(host='www.jstage.jst.go.jp', port=443): Max retries exceeded with url: /robots.txt (Caused by ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed: 403 Forbidden'))) -> unreachable (RFC 9309 2.3.1.4) |  |
| argondigital.com | open | open 1 | 2026-11-09T23:20:47Z |  |  |
| arxiv.org | open | open 16 | 2026-11-09T23:36:21.667713+00:00 | HTTP 200 OK at https://arxiv.org/pdf/2512.24601; robots.txt HTTP 200 -> successful (RFC 9309 2.3.1.1); Allow: /pdf (line 11); text taken |  |
| cog.readthedocs.io | open | open 1 | 2026-11-09T23:20:40Z |  |  |
| danieleades.github.io | open | open 1 | 2026-11-09T23:20:43Z |  |  |
| doorstop-dev.github.io | open | open 1 | 2026-11-09T23:20:40Z |  |  |
| raw.githubusercontent.com | open | open 6 | 2026-11-09T23:20:47Z |  |  |
| sphinx-needs.readthedocs.io | open | open 2 | 2026-11-09T23:20:43Z |  |  |
| strictdoc.readthedocs.io | open | open 1 | 2026-11-09T23:20:42Z |  |  |
| www.omg.org | open | open 3 | 2026-11-09T23:22:02Z |  |  |

45 entries carry a posture; 13 were attempted with no host observed (the kit declined to ask: R-148).

Human-in-the-loop share (R-245): 7 of 45 observed text-expecting entries (15.56%); 61 of 106 not yet observed (6.60% of all).
By posture: {'not_observed': 61, 'open': 32, 'refused': 7, 'unreachable': 6}.
