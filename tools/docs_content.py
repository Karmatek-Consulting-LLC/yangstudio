"""Page content for the documentation site.

Kept separate from the chrome in build_docs.py so the prose is editable
without wading through boilerplate. Every measurement quoted here was taken
from a real run, not estimated.
"""
from __future__ import annotations


def build(fig, IMAGE, REPO):
    pages = []

    # ---------------------------------------------------------------- index
    pages.append(("index", "YANG Studio",
        "Browse the YANG models a device implements, then build and run NETCONF "
        "or RESTCONF requests against it from the same tree.", f"""
    <div class="prose">
      <h1>Browse a device's YANG models, then drive it</h1>
      <p class="lede">Connect over NETCONF, download the schemas the device
      advertises, explore them as a tree, and build requests from that tree —
      as NETCONF XML or RESTCONF URLs, run against the live device.</p>

      <pre><b>docker run</b> -p 8420:8420 -v yangstudio-data:/data \\
  {IMAGE}:latest</pre>
      <p>Then open <a href="http://localhost:8420">localhost:8420</a>.</p>
    </div>

    {fig("explore-tree", "The schema tree for a set of 13 modules — 199 nodes, parsed in under half a second.", wide=True)}

    <div class="prose">
      <h2 id="what">What it does</h2>

      <h3>Reads schemas off the device</h3>
      <p>A NETCONF session tells you every module the device implements, with
      the revision, the optional features it turned on, and the vendor
      deviations it applies. Download the ones you want — in the background,
      with progress you can walk away from.</p>

      <h3>Parses them into something you can navigate</h3>
      <p>The tree is virtualised, so a set with a hundred thousand nodes scrolls
      at full speed. Filtering is live, and matches keep their ancestors so you
      can see where a result sits rather than getting a flat list of names.</p>

      <h3>Tells you what a node actually is</h3>
      <p>Type and the typedef chain beneath it, range and pattern constraints,
      allowed values, both paths, and whether it is
      <span class="tag tag-config">config</span> you can write or
      <span class="tag tag-state">state</span> the device reports.</p>

      <h3>Builds requests from the tree</h3>
      <p>Tick nodes and the request is written as you go — NETCONF XML, or the
      RESTCONF method, URL and JSON body. Run either against a device and read
      the reply formatted and highlighted.</p>

      <h2 id="themes">Light and dark</h2>
      <p>The interface follows your system theme, and can be switched from the
      top bar.</p>
    </div>

    {fig("explore-light", "The same view in the light theme.", wide=True)}

    <div class="prose">
      <h2 id="next">Where to go next</h2>
      <div class="cards">
        <a class="card" href="/getting-started">
          <h3>Getting started →</h3>
          <p>From an empty install to a request running against your device.</p>
        </a>
        <a class="card" href="/concepts">
          <h3>YANG concepts →</h3>
          <p>What a capability string is, what you download, and why a
          repository and a set are different things.</p>
        </a>
        <a class="card" href="/netconf">
          <h3>NETCONF →</h3>
          <p>Filters, datastores, and why a write may need a commit.</p>
        </a>
        <a class="card" href="/restconf">
          <h3>RESTCONF →</h3>
          <p>The same tree over HTTP, and where the two protocols differ.</p>
        </a>
      </div>
    </div>
"""))

    # ------------------------------------------------------ getting started
    pages.append(("getting-started", "Getting started",
        "From an empty install to a NETCONF or RESTCONF request running against "
        "your device.", f"""
    <div class="prose">
      <h1>Getting started</h1>
      <p class="lede">Five steps: add a device, download its schemas, make a
      set, explore it, run a request.</p>

      <div class="warn-box">
        <p><b>NETCONF needs AAA on IOS-XE.</b> Without it the session opens,
        the subsystem starts, and the device hangs up without saying anything —
        which looks like a credential problem but is not.</p>
        <pre>aaa new-model
aaa authentication login default local
aaa authorization exec default local</pre>
        <p>The account also needs privilege 15. If this is missing, YANG Studio
        says so explicitly rather than reporting a generic failure.</p>
      </div>

      <div class="steps">
        <div class="step"><div>
          <h3>Add the device and connect</h3>
          <p>On <b>Devices</b>, add a profile with an address, username and
          password, then press <b>Connect</b>. The session lists every module
          the device advertises — 507 on the box below.</p>
          <p>The family filters matter: roughly a third of that list is legacy
          SNMP MIBs translated to YANG, which are rarely what you want.</p>
        </div></div>
      </div>
    </div>

    {fig("devices-capabilities", "A connected device. 507 advertised modules, grouped by family — 174 of them SNMP MIBs.", wide=True)}

    <div class="prose">
      <div class="steps">
        <div class="step"><div>
          <h3>Download the schemas you want</h3>
          <p>Advertising a module is a promise, not the schema — the device has
          not sent you anything yet. Tick what you need, choose a repository (or
          create one right there), and press <b>Download</b>.</p>
          <p>Each module is a separate request, around a second each, so this
          runs as a background job. You can leave the page; it survives a
          reload, and the task bar at the bottom tracks it.</p>
        </div></div>

        <div class="step"><div>
          <h3>Make a set</h3>
          <p>A repository is the files you have. A <b>set</b> is a group of
          modules that resolve together into one tree — which is what you
          actually explore. When a download finishes, the task bar offers to
          make one from exactly what it fetched.</p>
          <p>Imports are pulled in automatically. If something is still
          missing, the app names it and offers to fetch it, because the device
          advertises those too.</p>
          <p><a href="/concepts#repo-vs-set">Why these are two different
          things →</a></p>
        </div></div>

        <div class="step"><div>
          <h3>Explore it</h3>
          <p>Pick the set on <b>Explore</b>. Click any node to see everything
          known about it. Filter by name, path, type or description — matches
          keep their ancestors so you can see the context.</p>
        </div></div>
      </div>
    </div>

    {fig("node-detail", "A leaf, with its type, description, constraints and both paths.", wide=True)}

    <div class="prose">
      <div class="steps">
        <div class="step"><div>
          <h3>Build a request and run it</h3>
          <p>Tick nodes in the tree, or highlight one and press
          <kbd>Space</kbd>. The request is written as you select. Choose
          NETCONF or RESTCONF, pick the device, and <b>Run</b>.</p>
        </div></div>
      </div>

      <h2 id="keyboard">Keyboard</h2>
      <div class="scroll"><table>
        <thead><tr><th>Key</th><th>Does</th></tr></thead>
        <tbody>
          <tr><td><code>⌘K</code> / <code>Ctrl-K</code></td><td>Command palette — actions and every loaded node</td></tr>
          <tr><td><code>1</code> <code>2</code> <code>3</code></td><td>Switch page</td></tr>
          <tr><td><code>↑</code> <code>↓</code></td><td>Move through the tree</td></tr>
          <tr><td><code>→</code> <code>←</code></td><td>Expand, collapse, or jump to the parent</td></tr>
          <tr><td><code>Enter</code></td><td>Inspect the highlighted node</td></tr>
          <tr><td><code>Space</code></td><td>Add or remove it from the request</td></tr>
        </tbody>
      </table></div>
      <p class="lede" style="font-size:.9rem">Tree keys work while the tree has
      focus — click it once and the legend under it lights up.</p>
    </div>

    {fig("command-palette", "The command palette searches actions and every node in the loaded set.", wide=True)}
"""))


    # ------------------------------------------------------------- concepts
    pages.append(("concepts", "YANG concepts",
        "What a capability string is, what you are downloading, why imports are "
        "not optional, and why a repository and a set are different things.", f"""
    <div class="prose">
      <h1>YANG, from inside the app</h1>
      <p class="lede">Every example here is real output from a Cisco IOS-XE
      device. Nothing is invented.</p>

      <div class="note">
        <p><b>The one idea: YANG is a schema language, not a protocol.</b></p>
        <p>A <code>.yang</code> file describes what data a device holds — the
        shape of the tree, the type of every leaf, which parts are
        configurable. It says nothing about how you read or write that data.
        NETCONF, RESTCONF and gNMI are three transports carrying
        <em>the same tree</em>.</p>
      </div>

      <h2 id="connect">What comes back when you connect</h2>
      <p>A NETCONF session opens with both sides announcing what they support.
      This device sends back <b>522 capability strings</b>: 15 describing the
      protocol, 507 describing YANG modules. Here is one of the 507, exactly as
      it arrived:</p>

      <pre>urn:ietf:params:xml:ns:yang:ietf-interfaces?module=<b>ietf-interfaces</b>&amp;revision=<span class="warn">2014-05-08</span>
  &amp;features=<span class="ok">pre-provisioning,if-mib,arbitrary-names</span>
  &amp;deviations=<span class="warn">cisco-xe-ietf-ip-deviation</span></pre>

      <div class="scroll"><table>
        <thead><tr><th>Part</th><th>Means</th></tr></thead>
        <tbody>
          <tr><td><code>namespace</code></td><td>The module's globally unique identity — what <code>xmlns</code> points at in a request.</td></tr>
          <tr><td><code>module</code></td><td>Its name. <b>This is the thing you download.</b></td></tr>
          <tr><td><code>revision</code></td><td>Which dated version the device implements.</td></tr>
          <tr><td><code>features</code></td><td>Optional parts it actually implements. Anything behind a feature flag not listed here <b>is not on this box</b>.</td></tr>
          <tr><td><code>deviations</code></td><td>Where the vendor departs from the standard module. Named modules, themselves downloadable.</td></tr>
        </tbody>
      </table></div>

      <div class="warn-box">
        <p><b>This is a promise, not the schema.</b> The device is saying "I
        implement ietf-interfaces at this revision". It has not sent you the
        model, and you still do not know what is in it.</p>
      </div>

      <h2 id="download">What you are downloading</h2>
      <p>Pressing Download issues one <code>&lt;get-schema&gt;</code> request
      per module, and the device returns the module's source. That text
      <em>is</em> the schema, and reading it is the fastest way into YANG:</p>

      <pre><b>container</b> interfaces {{          <span class="c">// a fixed node — exists once</span>
  <b>list</b> interface {{             <span class="c">// repeats; one entry per interface</span>
    <b>key</b> "name";                <span class="c">// what makes each entry unique</span>

    <b>leaf</b> name {{                <span class="c">// a single value...</span>
      <b>type</b> string;             <span class="c">// ...of this type</span>
    }}
    <b>leaf</b> enabled {{
      <b>type</b> boolean;
      <b>default</b> true;
    }}
  }}
}}</pre>
      <p>Four keywords carry most of YANG. <b>container</b> groups.
      <b>list</b> repeats and needs a <b>key</b>. <b>leaf</b> holds one typed
      value. Everything else refines those.</p>

      <h2 id="imports">Why it asks for other modules too</h2>
      <p>Modules borrow types from each other, and say so at the top:</p>
      <pre><span class="c">// in ietf-ip.yang</span>
<b>import</b> ietf-inet-types {{ <b>prefix</b> inet; }}

<span class="c">// and later</span>
<b>leaf</b> address {{ <b>type</b> <span class="hl">inet:ipv4-address-no-zone</span>; }}</pre>
      <p>What is an <code>ipv4-address-no-zone</code>? Nothing in
      <code>ietf-ip</code> answers that — the definition lives in the other
      file, as a string with a validation pattern. Without it the parser
      genuinely cannot tell you what that leaf accepts.</p>
      <p>That is what <em>"will not parse yet — 4 imports missing"</em> means.
      It is not fussiness; the tree cannot be built.</p>

      <h2 id="repo-vs-set">Why a repository <em>and</em> a set</h2>
      <p>They answer different questions, and this is the distinction that
      trips people up.</p>
      <div class="cards">
        <div class="card">
          <h3>Repository</h3>
          <p><b>"What files do I have?"</b> A directory of <code>.yang</code>
          files. An inventory. It may hold the same module at several
          revisions, and modules that contradict each other. A filing cabinet
          is not required to be consistent.</p>
        </div>
        <div class="card">
          <h3>Set</h3>
          <p><b>"Which modules resolve into one valid tree?"</b> Specific
          modules at specific revisions that parse together. This is the unit
          you explore and query, and it must be internally consistent.</p>
        </div>
      </div>

      <p>Why a repository cannot simply be parsed whole — two measurements:</p>
      <div class="scroll"><table>
        <thead><tr><th>Parsed</th><th>Modules</th><th>Result</th></tr></thead>
        <tbody>
          <tr><td>Every BFD module together</td><td>35</td><td><b>5 errors</b> — they all augment the same routing path and collide</td></tr>
          <tr><td>One BFD module</td><td>9</td><td><b>0 errors</b>, 250 nodes</td></tr>
        </tbody>
      </table></div>
      <p>On top of that, 23 module names in the IETF collection exist at two
      different revisions, and a tree can only use one. So there is no such
      thing as "the tree for this repository" — a set is what makes a tree
      possible at all.</p>

    </div>

    {fig("models", "Repositories on the left, their modules in the middle, sets on the right.", wide=True)}

    <div class="prose">
      <h2 id="using-a-set">What a set gets you</h2>
      <p>Every node carries two things that matter for doing work. First, a
      path that addresses it:</p>
      <pre>/if:interfaces/if:interface/if:description</pre>
      <p>Second, whether you can write to it. YANG marks operational data
      <code>config false</code>, and the app shows that as a badge:</p>
      <div class="scroll"><table>
        <thead><tr><th>Badge</th><th>Means</th><th>Example</th></tr></thead>
        <tbody>
          <tr><td><span class="tag tag-config">config</span></td><td>Read <em>and</em> write</td><td><code>interface/description</code></td></tr>
          <tr><td><span class="tag tag-state">state</span></td><td>Read-only — the device reports it</td><td><code>interface/oper-status</code></td></tr>
        </tbody>
      </table></div>
      <p>Trying to write a state node is one of the commonest early mistakes.
      The tree tells you before you try.</p>

      <h3>Features narrow the tree</h3>
      <p>Because the device declared it implements
      <code>pre-provisioning, if-mib, arbitrary-names</code> and nothing else,
      a set built from its capabilities prunes what is not there — on this
      device that removed <code>if-index</code> and
      <code>link-up-down-trap-enable</code>. Small here; on a full vendor
      model it is the difference between a schema and a schema that matches the
      box in front of you.</p>
    </div>

    {fig("identityref-values", "An identityref resolves through the whole identity hierarchy, not one level.", wide=True)}

    <div class="prose">
      <h2 id="vocabulary">The vocabulary</h2>
      <p>Everything you will meet in the tree. The first four are ninety
      percent of it.</p>
      <div class="scroll"><table>
        <tbody>
          <tr><td><code>container</code></td><td>Groups other nodes. Exists once.</td></tr>
          <tr><td><code>list</code></td><td>Repeats — one entry per interface, per neighbour. Needs a <b>key</b>.</td></tr>
          <tr><td><code>leaf</code></td><td>One typed value. The actual data.</td></tr>
          <tr><td><code>leaf-list</code></td><td>A leaf holding several values of one type.</td></tr>
          <tr><td><code>key</code></td><td>The leaf making a list entry unique. Becomes a path segment when addressing one entry.</td></tr>
          <tr><td><code>config false</code></td><td>Read-only operational state.</td></tr>
          <tr><td><code>typedef</code></td><td>A named reusable type, often with a pattern or range. Frequently in another module.</td></tr>
          <tr><td><code>identity</code> / <code>identityref</code></td><td>An extensible enumeration. <code>interface/type</code> is one.</td></tr>
          <tr><td><code>feature</code></td><td>An optional part of a module. The device says which it implements.</td></tr>
          <tr><td><code>deviation</code></td><td>A vendor's documented departure from a standard module.</td></tr>
          <tr><td><code>augment</code></td><td>One module adding nodes into another's tree — and the reason modules can collide.</td></tr>
          <tr><td><code>choice</code> / <code>case</code></td><td>Mutually exclusive alternatives.</td></tr>
          <tr><td><code>rpc</code> / <code>action</code></td><td>An operation you invoke, with <b>input</b> and <b>output</b>.</td></tr>
          <tr><td><code>notification</code></td><td>An event the device can push.</td></tr>
          <tr><td><code>prefix</code></td><td>The short alias for a namespace, seen throughout paths: <code>if:interfaces</code>.</td></tr>
        </tbody>
      </table></div>
    </div>
"""))


    # -------------------------------------------------------------- netconf
    pages.append(("netconf", "NETCONF",
        "Subtree filters, datastores, and why a write may need a commit.", f"""
    <div class="prose">
      <h1>NETCONF</h1>
      <p class="lede">Tick nodes, and the XML is written as you select. One
      filter can carry several branches at once, which is the main thing that
      distinguishes it from RESTCONF.</p>

      <h2 id="reading">Reading</h2>
      <p>Selecting three leaves under one list produces a single
      <code>get-config</code> whose subtree filter names all three. Sibling
      selections merge under a shared parent rather than repeating it:</p>
      <pre>&lt;<b>get-config</b>&gt;
  &lt;source&gt;&lt;running/&gt;&lt;/source&gt;
  &lt;filter type="subtree"&gt;
    &lt;interfaces xmlns="urn:ietf:params:xml:ns:yang:ietf-interfaces"&gt;
      &lt;interface&gt;
        &lt;<span class="hl">name</span>/&gt;
        &lt;<span class="hl">description</span>/&gt;
        &lt;<span class="hl">type</span>/&gt;
      &lt;/interface&gt;
    &lt;/interfaces&gt;
  &lt;/filter&gt;
&lt;/<b>get-config</b>&gt;</pre>
      <p>Give a key leaf a value and it becomes a filter match, narrowing the
      reply to that entry.</p>
    </div>

    {fig("request-netconf", "Three selected leaves, and the XML written from them.", wide=True)}

    <div class="prose">

      <h2 id="reply">The reply</h2>
      <p>Devices send a reply as one long line, which is correct on the wire
      and unreadable on screen. It is re-indented and highlighted before you
      see it.</p>
    </div>

    {fig("response-netconf", "The same request run, and its reply.", wide=True)}

    <div class="prose">
      <h2 id="datastores">Datastores</h2>
      <p>NETCONF separates the configuration that is running from the one you
      are editing. Which datastores exist depends on the device, and YANG
      Studio reads that from its capabilities.</p>
      <div class="scroll"><table>
        <thead><tr><th>Datastore</th><th>Is</th></tr></thead>
        <tbody>
          <tr><td><code>running</code></td><td>The live configuration. Writable only if the device advertises <code>:writable-running</code>.</td></tr>
          <tr><td><code>candidate</code></td><td>A scratch copy. Edits land here and take effect on <b>commit</b>.</td></tr>
          <tr><td><code>startup</code></td><td>What the device loads at boot, where supported.</td></tr>
        </tbody>
      </table></div>

      <h2 id="writing">Writing, and why commit matters</h2>
      <div class="warn-box">
        <p><b>Many devices refuse a direct write to running.</b> IOS-XR and
        Junos always; IOS-XE once <code>candidate-datastore</code> is enabled.
        There, an edit-config against <code>running</code> comes back:</p>
        <pre>Unsupported capability :writable-running</pre>
        <p>The flow is edit into <code>candidate</code>, then commit. Without
        that second step the edit is discarded when the session ends — and a
        successful-looking reply would imply a change that never happened.</p>
      </div>

      <p>YANG Studio marks a staged edit rather than letting it look applied:</p>
      <pre><span class="warn">Staged in candidate — not applied yet.</span>   [ Commit ]  [ Discard ]</pre>

      <p>The full sequence, as measured against a live IOS-XE device:</p>
      <div class="scroll"><table>
        <thead><tr><th>Step</th><th>Operation</th><th>Took</th></tr></thead>
        <tbody>
          <tr><td>1</td><td><code>edit-config</code> into <code>candidate</code></td><td>5.3 s</td></tr>
          <tr><td>2</td><td><code>validate</code> the candidate</td><td>2.8 s</td></tr>
          <tr><td>3</td><td><code>commit</code></td><td>19 s</td></tr>
        </tbody>
      </table></div>
      <div class="note">
        <p>A commit is slow because the device is applying configuration. On
        the same device a second commit took <b>52 s</b>. The default reply
        timeout is 60 s — raise <code>YANGSTUDIO_RPC_TIMEOUT</code> if your
        commits run long.</p>
      </div>

      <h3>Confirmed commit</h3>
      <p>Where the device supports it, a commit can be conditional: it rolls
      back automatically unless a second commit confirms within the timeout.
      That is the safety net for a change that might cut off your own
      access.</p>
      <pre>&lt;<b>commit</b>&gt;
  &lt;confirmed/&gt;
  &lt;confirm-timeout&gt;<span class="hl">120</span>&lt;/confirm-timeout&gt;
&lt;/<b>commit</b>&gt;</pre>

      <h2 id="operations">Per-node operations</h2>
      <p>In an <code>edit-config</code>, each selected node can carry its own
      operation, so one request can merge one leaf and delete another
      atomically.</p>
      <div class="scroll"><table>
        <thead><tr><th>Operation</th><th>Does</th></tr></thead>
        <tbody>
          <tr><td><code>merge</code></td><td>Set the value, leaving siblings alone. The default.</td></tr>
          <tr><td><code>replace</code></td><td>Replace the node and everything under it.</td></tr>
          <tr><td><code>create</code></td><td>Set it, failing if it already exists.</td></tr>
          <tr><td><code>delete</code></td><td>Remove it, failing if it is absent.</td></tr>
          <tr><td><code>remove</code></td><td>Remove it, succeeding either way.</td></tr>
        </tbody>
      </table></div>

      <h2 id="sessions">Sessions</h2>
      <p>Connections are reused rather than reopened per request. If an RPC
      times out the session is dropped rather than reused — a late reply
      arriving against a message-id already moved past desynchronises the
      channel, and every later request would time out too. Retrying
      reconnects.</p>
    </div>
"""))

    # ------------------------------------------------------------- restconf
    pages.append(("restconf", "RESTCONF",
        "The same tree over HTTP: path encoding, fields queries, and where it "
        "differs from NETCONF.", f"""
    <div class="prose">
      <h1>RESTCONF</h1>
      <p class="lede">The same tree, encoded per RFC 8040. Switch protocol in
      the request panel and the selection you already built renders as a
      method, a URL and a JSON body.</p>

      <h2 id="paths">How a path becomes a URL</h2>
      <p>Three rules do most of the work.</p>
      <ul>
        <li>The first node is qualified by its module — <code>ietf-interfaces:interfaces</code></li>
        <li>Later nodes are bare, unless an augment changes module, which re-qualifies them</li>
        <li>A list entry carries its keys in the path — <code>interface=GigabitEthernet1</code></li>
      </ul>
      <pre><span class="c"># the YANG path</span>
/if:interfaces/if:interface/if:description

<span class="c"># the same node, addressed over RESTCONF</span>
GET /restconf/data/<b>ietf-interfaces:interfaces</b>/interface=<span class="hl">GigabitEthernet1</span>/description</pre>

      <div class="note">
        <p><b>Keys are percent-encoded.</b> This matters immediately on Cisco
        kit — <code>Gi0/0/1</code> becomes <code>Gi0%2F0%2F1</code>, because an
        unescaped slash would look like another path segment.</p>
      </div>

      <h2 id="one-resource">One resource per request</h2>
      <p>This is the real difference. A NETCONF filter carries several branches
      at once; RESTCONF addresses one resource per call. Several leaves under
      one parent fold into a single request using a <code>fields</code>
      query:</p>
      <pre>GET /restconf/data/ietf-interfaces:interfaces/interface<span class="hl">?fields=name;description;type</span></pre>
      <p>Anything that cannot fold becomes its own request, and the panel says
      so rather than hiding it. Each request lists which tree paths it
      covers.</p>
    </div>

    {fig("response-restconf", "Three leaves folded into one fields query, and the JSON reply.", wide=True)}

    <div class="prose">
      <h2 id="writing">Writing</h2>
      <p>NETCONF's edit operations map onto HTTP methods. The body names its
      member with the module that defines it:</p>
      <div class="scroll"><table>
        <thead><tr><th>NETCONF</th><th>RESTCONF</th><th>Means</th></tr></thead>
        <tbody>
          <tr><td><code>merge</code></td><td><span class="tag tag-write">PATCH</span></td><td>Merge into the resource</td></tr>
          <tr><td><code>replace</code></td><td><span class="tag tag-write">PUT</span></td><td>Create or replace it</td></tr>
          <tr><td><code>create</code></td><td><span class="tag tag-write">POST</span></td><td>Create a child</td></tr>
          <tr><td><code>delete</code> / <code>remove</code></td><td><span class="tag tag-del">DELETE</span></td><td>Remove it</td></tr>
        </tbody>
      </table></div>
      <pre>PATCH /restconf/data/ietf-interfaces:interfaces/interface=GigabitEthernet1/description
Content-Type: application/yang-data+json

{{
  "<b>ietf-interfaces:description</b>": "uplink"
}}</pre>

      <div class="warn-box">
        <p><b>There is no candidate datastore.</b> RFC 8040 has no staging area
        and no commit — a write lands immediately on the running configuration.
        If you want to stage a change, validate it, and apply it as one
        transaction, that is <a href="/netconf#writing">NETCONF</a>.</p>
      </div>

      <h2 id="checking">Checking a device supports it</h2>
      <p>RESTCONF has no handshake, so without asking you only find out when a
      request fails. <b>Check RESTCONF</b> on the Devices page reports the root
      and the optional capabilities that decide what a request can express —
      <code>fields</code> is the one that makes the folding above legal.</p>

      <h2 id="differences">Where the two differ</h2>
      <div class="scroll"><table>
        <thead><tr><th></th><th>NETCONF</th><th>RESTCONF</th></tr></thead>
        <tbody>
          <tr><td>Transport</td><td>SSH, port 830</td><td>HTTPS, port 443</td></tr>
          <tr><td>Encoding</td><td>XML</td><td>JSON or XML</td></tr>
          <tr><td>Per request</td><td>Several branches in one filter</td><td>One resource</td></tr>
          <tr><td>Staging</td><td>candidate + commit</td><td>None — writes are immediate</td></tr>
          <tr><td>Transactions</td><td>Yes, with confirmed-commit</td><td>No</td></tr>
        </tbody>
      </table></div>
    </div>
"""))


    # --------------------------------------------------------------- deploy
    pages.append(("deploy", "Deploying",
        "Docker, Compose, what the volume holds, and every configuration "
        "variable.", f"""
    <div class="prose">
      <h1>Deploying</h1>
      <p class="lede">One container, one volume. The image serves the API and
      the UI from a single process and runs as a non-root user.</p>

      <h2 id="docker">Docker</h2>
      <pre><b>docker run</b> -d --name yangstudio \
  -p 8420:8420 \
  -v yangstudio-data:/data \
  {IMAGE}:latest</pre>
      <p>Built for <code>linux/amd64</code> and <code>linux/arm64</code>, with
      an SBOM and build provenance attached.</p>

      <h2 id="compose">Docker Compose</h2>
      <pre>services:
  yangstudio:
    image: {IMAGE}:latest
    ports:
      - "8420:8420"
    volumes:
      - yangstudio-data:<b>/data</b>
    restart: unless-stopped

volumes:
  yangstudio-data:</pre>
      <pre>docker compose up -d</pre>

      <h2 id="volume">The volume</h2>
      <div class="warn-box">
        <p><b>Mount <code>/data</code> or you will lose everything you
        download.</b> It holds your repositories, sets and device profiles, and
        a container without it starts empty every time it is replaced.</p>
      </div>
      <p>Its layout is deliberately plain, so it is readable and diffable
      without the app:</p>
      <pre>/data
├── repositories/&lt;name&gt;/*.yang   <span class="c"># plain YANG files</span>
├── yangsets/&lt;name&gt;.json         <span class="c"># which modules, at which revisions</span>
├── devices/&lt;name&gt;.json          <span class="c"># connection profiles</span>
└── cache/                       <span class="c"># header index, safe to delete</span></pre>

      <p>To keep it somewhere you can see, bind-mount a directory instead:</p>
      <pre>    volumes:
      - <b>./yangstudio-data</b>:/data</pre>

      <div class="warn-box">
        <p><b>Device passwords are stored in plain text</b> in
        <code>/data/devices/*.json</code>, because the app must replay them to
        authenticate. Treat that volume as a secret: keep it off shared
        storage, and out of version control.</p>
      </div>

      <h2 id="config">Configuration</h2>
      <p>All optional.</p>
      <div class="scroll"><table>
        <thead><tr><th>Variable</th><th>Default</th><th>Means</th></tr></thead>
        <tbody>
          <tr><td><code>YANGSTUDIO_DATA</code></td><td><code>~/.yangstudio</code></td><td>Where repositories, sets and profiles live. <code>/data</code> in the image.</td></tr>
          <tr><td><code>YANGSTUDIO_HOST</code></td><td><code>127.0.0.1</code></td><td>Bind address. <code>0.0.0.0</code> in the image.</td></tr>
          <tr><td><code>YANGSTUDIO_PORT</code></td><td><code>8420</code></td><td>Port for both API and UI.</td></tr>
          <tr><td><code>YANGSTUDIO_RPC_TIMEOUT</code></td><td><code>60</code></td><td>Seconds to wait for a NETCONF reply. A commit on a busy device can use most of it.</td></tr>
          <tr><td><code>YANGSTUDIO_CORS</code></td><td><code>localhost:5173</code></td><td>Allowed origins, comma-separated.</td></tr>
          <tr><td><code>YANGSTUDIO_STATIC</code></td><td>auto</td><td>Path to the built frontend.</td></tr>
        </tbody>
      </table></div>

      <h2 id="memory">Sizing</h2>
      <p>Parsing is the expensive step and it is proportional to the set you
      open, not to the repository. Measured on the IETF RFC collection:</p>
      <div class="scroll"><table>
        <thead><tr><th>Operation</th><th>Cost</th></tr></thead>
        <tbody>
          <tr><td>Index a 484-module repository</td><td>0.33 s — headers only</td></tr>
          <tr><td>Parse a 144-module set (11,403 nodes)</td><td>10.9 s</td></tr>
          <tr><td>Re-open the same set</td><td>0.08 s, from cache</td></tr>
          <tr><td>Search across 11,403 nodes</td><td>0.02 s</td></tr>
        </tbody>
      </table></div>
      <p>Large vendor-native sets are memory-hungry; a few gigabytes is
      reasonable for those. A handful of IETF modules needs very little.</p>

      <h2 id="source">From source</h2>
      <p>Needs <a href="https://docs.astral.sh/uv/">uv</a> and Node 22+.</p>
      <pre>git clone {REPO}
cd yangstudio
./run.sh</pre>
      <p>The script creates the virtualenv, installs dependencies, finds free
      ports — 8420 and 5173 are commonly taken — and prints both URLs.</p>
    </div>
"""))


    # ------------------------------------------------------------------ api
    pages.append(("api", "HTTP API",
        "Every endpoint, generated from the running service's OpenAPI schema.",
        _api_body(REPO)))

    return pages

def _api_body(REPO: str) -> str:
    """Render the endpoint reference from the checked-in OpenAPI schema.

    Generated rather than written so it cannot drift from the service. Refresh
    with:  curl -s localhost:8420/openapi.json > tools/openapi.json
    """
    import json
    from pathlib import Path

    spec_path = Path(__file__).resolve().parent / "openapi.json"
    spec = json.loads(spec_path.read_text())

    groups: dict[str, list] = {}
    for path, methods in spec["paths"].items():
        for method, op in methods.items():
            summary = op.get("summary") or ""
            doc = (op.get("description") or "").strip().split("\n\n")[0]
            # Group by the first path segment after /api.
            parts = [p for p in path.split("/") if p and p != "api"]
            section = parts[0] if parts else "root"
            groups.setdefault(section, []).append((method.upper(), path, summary, doc))

    order = ["health", "repositories", "yangsets", "explore", "devices",
             "netconf", "restconf", "rpc", "jobs"]
    keys = [k for k in order if k in groups] + sorted(set(groups) - set(order))

    verb_class = {"GET": "tag-get", "POST": "tag-write", "PATCH": "tag-write",
                  "PUT": "tag-write", "DELETE": "tag-del"}

    rows = []
    for key in keys:
        rows.append(f'      <h2 id="{key}">{key}</h2>')
        rows.append('      <div class="scroll"><table><tbody>')
        for method, path, summary, doc in sorted(groups[key], key=lambda r: (r[1], r[0])):
            cls = verb_class.get(method, "tag-get")
            text = doc or summary
            text = text.replace("<", "&lt;")
            rows.append(
                f'        <tr><td style="white-space:nowrap"><span class="tag {cls}">{method}</span></td>'
                f'<td style="white-space:nowrap"><code>{path}</code></td>'
                f"<td>{text}</td></tr>"
            )
        rows.append("      </table></div>")
    table = "\n".join(rows)

    count = sum(len(v) for v in groups.values())
    return f"""
    <div class="prose">
      <h1>HTTP API</h1>
      <p class="lede">{count} endpoints. Everything the UI does goes through
      these, so anything you can do in the browser you can script.</p>

      <div class="note">
        <p>The running service publishes an interactive schema at
        <code>/docs</code> and the raw document at <code>/openapi.json</code>.
        This page is generated from that schema, so it cannot drift.</p>
      </div>

      <h2 id="example">Example</h2>
      <p>Building a request without sending it — useful for seeing what a
      selection becomes:</p>
      <pre>curl -s localhost:8420/api/rpc/build \\
  -H 'content-type: application/json' \\
  -d '{{
    "operation": "get-config",
    "datastore": "running",
    "namespaces": {{"if": "urn:ietf:params:xml:ns:yang:ietf-interfaces"}},
    "selections": [{{"xpath": "/if:interfaces/if:interface/if:description"}}]
  }}'</pre>

{table}
    </div>
"""
