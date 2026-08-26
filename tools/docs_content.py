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
      <h1>Explore your device's YANG models</h1>
      <p class="lede">YANG Studio connects to your network devices, downloads
      the YANG models they publish, and lets you browse those models as a tree.
      When you find the data you are after, you can build a NETCONF or RESTCONF
      request from the tree and send it to the device without leaving the
      page.</p>

      <pre><b>docker run</b> --rm --name yangstudio \\
  -p 8420:8420 \\
  -v yangstudio-data:/data \\
  {IMAGE}:latest</pre>
      <p>Then open <a href="http://localhost:8420">localhost:8420</a>. Press
      <kbd>Ctrl-C</kbd> to stop it. The <code>--rm</code> flag tidies the
      container away afterwards but leaves the <code>yangstudio-data</code>
      volume alone, so everything you downloaded is still there next time.</p>
    </div>

    {fig("explore-tree", "The schema tree for a set of 13 modules — 199 nodes, parsed in under half a second.", wide=True)}

    <div class="prose">
      <h2 id="what">What it does</h2>

      <h3>Schema discovery</h3>
      <p>When you connect over NETCONF, the device lists every YANG module it
      implements, along with the revision it uses, the optional features it has
      turned on, and any vendor deviations it applies. You choose which of
      those modules to download. The download runs in the background, so you
      can carry on working or close the page while it finishes.</p>

      <h3>A tree you can actually navigate</h3>
      <p>The models are parsed into a browsable tree. Only the rows on screen
      are rendered, so even a set with a hundred thousand nodes scrolls
      smoothly. The filter box works as you type, and when a node matches, its
      parents stay visible around it — you see where the result sits in the
      model rather than a flat list of names with no context.</p>

      <h3>Full detail on every node</h3>
      <p>Selecting a node shows you its type and the chain of typedefs beneath
      it, any range or pattern constraints, the values it will accept, and both
      of the paths that address it. It also tells you whether the node is
      <span class="tag tag-config">config</span> that you can write to, or
      <span class="tag tag-state">state</span> that the device only reports.</p>

      <h3>Requests built from the model</h3>
      <p>As you tick nodes in the tree, the request is written for you: either
      the NETCONF XML, or the RESTCONF method, URL and JSON body. You can send
      it to the device from the same panel, and the reply comes back formatted
      and syntax-highlighted rather than as one long line.</p>

      <h2 id="themes">Light and dark</h2>
      <p>The interface follows whichever theme your system is set to, and you
      can override it from the button in the top bar.</p>
    </div>

    {fig("explore-light", "The same view in the light theme.", wide=True)}

    <div class="prose">
      <h2 id="next">Where to go next</h2>
      <div class="cards">
        <a class="card" href="/getting-started">
          <h3>Getting started →</h3>
          <p>Walk through the whole flow, from an empty install to a request
          running against one of your devices.</p>
        </a>
        <a class="card" href="/concepts">
          <h3>YANG concepts →</h3>
          <p>If the terminology is new to you, start here. It covers what a
          capability string is, what you are downloading, and why a repository
          and a set are two different things.</p>
        </a>
        <a class="card" href="/netconf">
          <h3>NETCONF →</h3>
          <p>How filters are built, what the datastores are for, and why a
          write to some devices needs a commit afterwards.</p>
        </a>
        <a class="card" href="/restconf">
          <h3>RESTCONF →</h3>
          <p>The same models over HTTP, how a YANG path becomes a URL, and
          where the two protocols part company.</p>
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
      <p class="lede">Once the device is running NETCONF or RESTCONF, there
      are five steps to get from a fresh install to a request running against
      it: add the device, download the schemas it publishes, group them into a
      set, explore that set, and send a request.</p>

      <h2 id="prepare">Preparing the device</h2>
      <p>Before YANG Studio can talk to anything, the device has to be running
      the services and willing to authorise them. On IOS-XE that is three
      pieces: AAA, the NETCONF service, and the RESTCONF service. The whole
      thing is ten lines, and this is a working configuration taken from a live
      router:</p>

      <pre>conf t

 <span class="c">! Both protocols authenticate through AAA. Without exec</span>
 <span class="c">! authorisation, NETCONF sessions open and are then dropped.</span>
 aaa new-model
 aaa authentication login default local
 aaa authorization exec default local

 <span class="c">! NETCONF — listens on port 830 over SSH.</span>
 netconf-yang

 <span class="c">! Optional, and worth having: adds a candidate datastore, so</span>
 <span class="c">! changes can be staged and committed as one transaction.</span>
 netconf-yang feature candidate-datastore

 <span class="c">! RESTCONF — needs the HTTPS server; it will not run over HTTP.</span>
 ip http secure-server
 ip http authentication local
 no ip http server
 restconf

end
write memory</pre>

      <div class="warn-box">
        <p><b>Apply the three AAA lines together.</b> <code>aaa new-model</code>
        on its own changes how every login is authenticated, and without the
        <code>aaa authentication login default local</code> line alongside it
        you can lock yourself out of SSH. All three together preserve the
        behaviour of a device using local accounts.</p>
        <p>If you are working on something you cannot easily get back to,
        <code>reload in 5</code> before you start is cheap insurance — the
        device reboots into its saved configuration if you lose access.</p>
      </div>

      <h3>What each part is for</h3>
      <div class="scroll"><table>
        <thead><tr><th>Line</th><th>Why</th></tr></thead>
        <tbody>
          <tr><td><code>aaa new-model</code><br><code>aaa authentication login default local</code><br><code>aaa authorization exec default local</code></td>
              <td>Both protocols authorise through AAA. Exec authorisation is the part people miss: without it the SSH login succeeds, the NETCONF subsystem starts, and the device then closes the session without a hello. It looks like a password problem and is not one.</td></tr>
          <tr><td><code>netconf-yang</code></td>
              <td>Starts NETCONF on port 830. This is the only line strictly required for it.</td></tr>
          <tr><td><code>netconf-yang feature candidate-datastore</code></td>
              <td>Adds the candidate datastore. Worth enabling — it is what lets a change be staged, validated and committed as one transaction. Note that it also stops the device accepting writes directly to <code>running</code>.</td></tr>
          <tr><td><code>ip http secure-server</code></td>
              <td>RESTCONF runs over HTTPS on port 443 and will not start without it.</td></tr>
          <tr><td><code>ip http authentication local</code></td>
              <td>Authenticate HTTPS against the local user database.</td></tr>
          <tr><td><code>no ip http server</code></td>
              <td>Turns plain HTTP off, so credentials are never sent unencrypted. Not required, but there is no reason to leave it on.</td></tr>
          <tr><td><code>restconf</code></td>
              <td>Starts RESTCONF itself.</td></tr>
        </tbody>
      </table></div>

      <h3>Checking it worked</h3>
      <p>Two commands tell you whether the device is ready, before you go
      anywhere near the app:</p>
      <pre>show netconf-yang status</pre>
      <pre>netconf-yang: <span class="ok">enabled</span>
netconf-yang ssh port: <span class="ok">830</span>
netconf-yang candidate-datastore: <span class="ok">enabled</span></pre>

      <pre>show platform software yang-management process</pre>
      <pre>confd            : <span class="ok">Running</span>
nesd             : <span class="ok">Running</span>
syncfd           : <span class="ok">Running</span>
ncsshd           : <span class="ok">Running</span>     <span class="c">&lt;- NETCONF over SSH</span>
<span class="hl">dmiauthd</span>         : <span class="ok">Running</span>     <span class="c">&lt;- authorises sessions; needs AAA</span>
nginx            : <span class="ok">Running</span>     <span class="c">&lt;- serves RESTCONF</span>
ndbmand          : <span class="ok">Running</span>
pubd             : <span class="ok">Running</span></pre>
      <p>If <code>dmiauthd</code> is not running, AAA is the thing to look at.
      If <code>nginx</code> is not running, RESTCONF has no web server. The
      account you connect with also needs privilege 15.</p>

      <div class="note">
        <p>These commands are IOS-XE, and were taken from a working router
        rather than from documentation. Other platforms enable the same two
        protocols with their own syntax — check your vendor's guide for those.
        Everything else in this documentation applies either way, since the
        models and the protocols are the same; only the lines that turn them on
        differ.</p>
      </div>

      <div class="steps">
        <div class="step"><div>
          <h3>Add the device and connect</h3>
          <p>Go to <b>Devices</b> and create a profile with the address,
          username and password for your device, then press <b>Connect</b>.
          YANG Studio opens a NETCONF session and lists every module the device
          says it implements. The router in the screenshot below advertises
          507 of them.</p>
          <p>That list is long, so it is grouped by family. Around a third of
          it is usually legacy SNMP MIBs that have been translated into YANG,
          and those are rarely what you are looking for.</p>
        </div></div>
      </div>
    </div>

    {fig("devices-capabilities", "A connected device. 507 advertised modules, grouped by family — 174 of them SNMP MIBs.", wide=True)}

    <div class="prose">
      <div class="steps">
        <div class="step"><div>
          <h3>Download the schemas you want</h3>
          <p>When a device advertises a module it is telling you that it
          implements it, but it has not sent you anything yet. To get the model
          itself you have to ask for it. Tick the modules you want, choose the
          repository to save them into (you can create one without leaving the
          page), and press <b>Download</b>.</p>
          <p>You do not have to work out what else a module needs. Each one
          that arrives is scanned for its imports, and anything missing is
          added to the queue and fetched too, the same way a package manager
          resolves a dependency tree. Asking for <code>ietf-ip</code> on the
          device in these examples brings down four modules, because it needs
          three others to be usable at all.</p>
          <p>Each module is a separate request to the device and takes roughly
          a second, so the download runs as a background job. You are free to
          navigate away or reload the page while it works — the task bar along
          the bottom keeps track of it, and the total climbs as dependencies
          are discovered.</p>
        </div></div>

        <div class="step"><div>
          <h3>Group the modules into a set</h3>
          <p>A repository is simply the collection of files you have downloaded.
          A <b>set</b> is a named group of modules that can be parsed together
          into a single tree, and the set is what you actually explore. When a
          download finishes, the task bar offers to build one from exactly the
          modules it just fetched.</p>
          <p>Because the download already pulled in everything the modules
          import, the set will usually parse the moment it is created. If
          something is still missing — a module the device names but will not
          serve, for instance — YANG Studio tells you which one and offers to
          fetch it.</p>
          <p><a href="/concepts#repo-vs-set">Why these are two different
          things →</a></p>
        </div></div>

        <div class="step"><div>
          <h3>Explore the set</h3>
          <p>Choose your set on the <b>Explore</b> page and the tree appears.
          Click on any node to see everything the model says about it. The
          filter box searches names, paths, types and descriptions at once, and
          anything that matches keeps its parent nodes visible so you can tell
          where in the model it lives.</p>
        </div></div>
      </div>
    </div>

    {fig("node-detail", "A leaf, with its type, description, constraints and both paths.", wide=True)}

    <div class="prose">
      <div class="steps">
        <div class="step"><div>
          <h3>Build a request and send it</h3>
          <p>Tick the nodes you are interested in, or highlight one and press
          <kbd>Space</kbd>. The request is written for you as you go. Choose
          whether to send it over NETCONF or RESTCONF, pick the device, and
          press <b>Run</b>.</p>
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
      <p>The tree shortcuts only work while the tree itself has keyboard
      focus. Click anywhere in it once and the legend along the bottom lights
      up to show that the keys are live.</p>
    </div>

    {fig("command-palette", "The command palette searches actions and every node in the loaded set.", wide=True)}
"""))


    # ------------------------------------------------------------- concepts
    pages.append(("concepts", "YANG concepts",
        "What a capability string is, what you are downloading, why imports are "
        "not optional, and why a repository and a set are different things.", f"""
    <div class="prose">
      <h1>YANG concepts</h1>
      <p class="lede">If the vocabulary around YANG is new to you, this page
      explains it through the things YANG Studio actually shows you. Every
      example below is real output from a Cisco IOS-XE device rather than an
      invented sample.</p>

      <div class="note">
        <p><b>The one idea worth starting with: YANG is a schema language,
        not a protocol.</b></p>
        <p>A <code>.yang</code> file describes the data a device holds. It
        defines the shape of the tree, the type of every leaf, and which parts
        of it you are allowed to change. What it does not describe is how you
        read or write any of that. NETCONF, RESTCONF and gNMI are three
        different ways of moving <em>the same tree</em> across the network, and
        learning the model is what carries across all three.</p>
      </div>

      <h2 id="connect">What comes back when you connect</h2>
      <p>When a NETCONF session opens, the client and the device each announce
      what they support. The device in this example sends back <b>522
      capability strings</b>: 15 that describe the protocol itself, and 507
      that describe the YANG modules it implements. Here is one of those 507,
      exactly as it arrived:</p>

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
        <p><b>A capability is a promise, not the schema itself.</b> The device
        is telling you that it implements <code>ietf-interfaces</code> at that
        revision. It has not sent you the model, so at this point you still do
        not know what is inside it. Downloading is a separate step.</p>
      </div>

      <h2 id="download">What you are downloading</h2>
      <p>When you press Download, YANG Studio sends one
      <code>&lt;get-schema&gt;</code> request for each module you picked, and
      the device replies with the module's source text. That text <em>is</em>
      the schema. It is meant to be read by people as well as parsers, and
      reading a little of it is the quickest way to get comfortable with
      YANG:</p>

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
      <p>Four keywords do most of the work in YANG. A <b>container</b> groups
      related nodes together and appears once. A <b>list</b> repeats, with one
      entry per interface or neighbour or route, and it needs a <b>key</b> to
      tell those entries apart. A <b>leaf</b> holds a single typed value, and
      that is where the actual data lives. Almost everything else in the
      language is a refinement of those four.</p>

      <h2 id="imports">Why it asks for other modules too</h2>
      <p>Modules are not self-contained. They borrow type definitions from one
      another, and they declare that at the top of the file:</p>
      <pre><span class="c">// in ietf-ip.yang</span>
<b>import</b> ietf-inet-types {{ <b>prefix</b> inet; }}

<span class="c">// and later</span>
<b>leaf</b> address {{ <b>type</b> <span class="hl">inet:ipv4-address-no-zone</span>; }}</pre>
      <p>So what is an <code>ipv4-address-no-zone</code>? Nothing in
      <code>ietf-ip</code> answers that question. The definition lives in the
      other file, where it turns out to be a string with a validation pattern
      attached. Without that second file, the parser genuinely cannot tell you
      what the leaf will accept, what to validate against, or what to suggest
      while you type.</p>
      <p>That is what the message <em>"will not parse yet — 4 imports
      missing"</em> is telling you. It is not the app being fussy. The tree
      cannot be built at all until those files are present.</p>

      <h2 id="repo-vs-set">Why a repository <em>and</em> a set</h2>
      <p>This is the distinction that catches most people out, and it is worth
      being precise about, because the two answer genuinely different
      questions.</p>
      <div class="cards">
        <div class="card">
          <h3>Repository</h3>
          <p><b>"What files do I have?"</b></p>
          <p>A repository is a directory of <code>.yang</code> files — an
          inventory of everything you have collected. It is allowed to hold the
          same module at several different revisions, and to hold modules that
          contradict one another. A filing cabinet does not have to be
          internally consistent.</p>
        </div>
        <div class="card">
          <h3>Set</h3>
          <p><b>"Which modules resolve into one valid tree?"</b></p>
          <p>A set names specific modules, at specific revisions, that can be
          parsed together successfully. This is the unit you explore and build
          requests against, and unlike a repository it does have to be
          consistent.</p>
        </div>
      </div>

      <p>You might reasonably ask why the app cannot just parse the whole
      repository and skip the extra step. These two measurements are the
      answer:</p>
      <div class="scroll"><table>
        <thead><tr><th>Parsed</th><th>Modules</th><th>Result</th></tr></thead>
        <tbody>
          <tr><td>Every BFD module together</td><td>35</td><td><b>5 errors</b> — they all augment the same routing path and collide</td></tr>
          <tr><td>One BFD module</td><td>9</td><td><b>0 errors</b>, 250 nodes</td></tr>
        </tbody>
      </table></div>
      <p>Those BFD modules all add nodes to the same place in the routing
      tree, so loading them together produces a genuine conflict. On top of
      that, 23 of the module names in the IETF collection exist at two
      different revisions, and a single tree can only use one of them. Between
      the two problems, there is no such thing as "the tree for this
      repository". Choosing a set is what makes a tree possible at all.</p>

    </div>

    {fig("models", "Repositories on the left, their modules in the middle, sets on the right.", wide=True)}

    <div class="prose">
      <h2 id="using-a-set">What a set gets you</h2>
      <p>Once a set is parsed, every node in it carries two pieces of
      information that you will use constantly. The first is a path that
      addresses it:</p>
      <pre>/if:interfaces/if:interface/if:description</pre>
      <p>The second is whether you are allowed to write to it. YANG marks
      operational data with <code>config false</code>, and YANG Studio turns
      that into a badge on every node:</p>
      <div class="scroll"><table>
        <thead><tr><th>Badge</th><th>Means</th><th>Example</th></tr></thead>
        <tbody>
          <tr><td><span class="tag tag-config">config</span></td><td>Read <em>and</em> write</td><td><code>interface/description</code></td></tr>
          <tr><td><span class="tag tag-state">state</span></td><td>Read-only — the device reports it</td><td><code>interface/oper-status</code></td></tr>
        </tbody>
      </table></div>
      <p>Attempting to write to a state node is one of the most common
      mistakes when you are starting out. The badge tells you before you
      try, rather than the device rejecting the request afterwards.</p>

      <h3>Features narrow the tree</h3>
      <p>Parts of a YANG module can be marked optional, and a device declares
      which of those it has turned on. The device in these examples implements
      <code>pre-provisioning</code>, <code>if-mib</code> and
      <code>arbitrary-names</code>, and nothing else. Because YANG Studio knows
      that, a set built from the device's own capabilities leaves out the nodes
      it does not support — here that removed <code>if-index</code> and
      <code>link-up-down-trap-enable</code>.</p>
      <p>The difference is small in this example, but on a full vendor model it
      is the difference between a schema for the product family and a schema
      for the box actually in front of you.</p>
    </div>

    {fig("identityref-values", "An identityref resolves through the whole identity hierarchy, not one level.", wide=True)}

    <div class="prose">
      <h2 id="vocabulary">The vocabulary</h2>
      <p>These are the terms you will run into while browsing a tree. As
      above, the first four account for the large majority of what you will
      see.</p>
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
      <p class="lede">As you tick nodes in the tree, YANG Studio writes the
      NETCONF XML for you. A single NETCONF filter can ask for several
      unrelated parts of the tree at once, which is the main thing that sets it
      apart from RESTCONF.</p>

      <div class="note">
        <p>The device needs <code>netconf-yang</code> configured, and AAA set
        up so it will authorise the session. See
        <a href="/getting-started#prepare">preparing the device</a>.</p>
      </div>

      <h2 id="reading">Reading</h2>
      <p>If you select three leaves that live under the same list, you get a
      single <code>get-config</code> whose filter names all three. Selections
      that share a parent are merged underneath it rather than each repeating
      the whole path:</p>
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
      <p>If you type a value into a key leaf, that value becomes part of the
      filter, and the device narrows its reply to the matching entry rather
      than returning every one.</p>
    </div>

    {fig("request-netconf", "Three selected leaves, and the XML written from them.", wide=True)}

    <div class="prose">

      <h2 id="reply">Reading the reply</h2>
      <p>Devices send their replies as a single unbroken line. That is perfectly
      correct on the wire and completely unreadable on screen, so YANG Studio
      re-indents and highlights the XML before showing it to you.</p>
    </div>

    {fig("response-netconf", "The same request run, and its reply.", wide=True)}

    <div class="prose">
      <h2 id="datastores">Datastores</h2>
      <p>NETCONF keeps the configuration that is currently running separate
      from the one you are editing. Which datastores a device offers varies,
      and YANG Studio works that out from the capabilities it advertised when
      you connected.</p>
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
        <p>On those devices the sequence is to edit into
        <code>candidate</code> and then commit. If you skip the commit, the
        edit is thrown away when the session closes, and the successful-looking
        reply from the first step would have implied a change that never
        actually happened.</p>
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
      <p>Within a single <code>edit-config</code>, every node you selected can
      carry its own operation. That means one request can merge a value into
      one leaf and delete another leaf entirely, and the device applies both as
      one change.</p>
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
      <p>YANG Studio keeps a NETCONF session open and reuses it, rather than
      reconnecting for every request. If a request does time out, the session
      is closed rather than reused: a reply that arrives late, against a
      message the client has already given up on, leaves the channel out of
      step, and every request after it would time out as well. Simply trying
      again reconnects and works.</p>
      <p>The same applies during a download. Devices close NETCONF sessions for
      their own reasons, and a long download is exactly when that tends to
      happen. When it does, the module that failed is retried once on a fresh
      session rather than being written off — and rather than every module
      after it failing on the same dead connection.</p>
    </div>
"""))

    # ------------------------------------------------------------- restconf
    pages.append(("restconf", "RESTCONF",
        "The same tree over HTTP: path encoding, fields queries, and where it "
        "differs from NETCONF.", f"""
    <div class="prose">
      <h1>RESTCONF</h1>
      <p class="lede">RESTCONF carries the same YANG models over ordinary
      HTTP, using the encoding defined in RFC 8040. Switch the protocol toggle
      in the request panel and the selection you have already built is
      re-rendered as an HTTP method, a URL, and a JSON body.</p>

      <div class="note">
        <p>The device needs <code>restconf</code> configured and the HTTPS
        server running — RESTCONF will not start over plain HTTP. See
        <a href="/getting-started#prepare">preparing the device</a>.</p>
      </div>

      <h2 id="paths">How a path becomes a URL</h2>
      <p>Three rules account for almost all of it.</p>
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
      <p>This is the substantive difference between the two protocols. A
      NETCONF filter can ask for several unrelated branches in one message,
      whereas a RESTCONF call addresses exactly one resource. Where several of
      your selected leaves share a parent, they are folded into a single
      request using a <code>fields</code> query:</p>
      <pre>GET /restconf/data/ietf-interfaces:interfaces/interface<span class="hl">?fields=name;description;type</span></pre>
      <p>Anything that cannot be folded in becomes a request of its own, and
      the panel tells you when that happens rather than quietly issuing extra
      calls. Each planned request lists the tree paths it covers, so you can
      see exactly which of your selections it accounts for.</p>
    </div>

    {fig("response-restconf", "Three leaves folded into one fields query, and the JSON reply.", wide=True)}

    <div class="prose">
      <h2 id="writing">Writing</h2>
      <p>The NETCONF edit operations have direct HTTP equivalents, so the same
      selection can be written either way. In the request body, the member is
      named with the module that defines it:</p>
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
      <p>Unlike NETCONF, RESTCONF has no handshake that announces itself, so
      if you do not ask, the first sign that it is unavailable is a request
      failing. The <b>Check RESTCONF</b> button on the Devices page asks the
      device directly and reports its root path along with the optional
      capabilities it supports. The one to look for is <code>fields</code>,
      since that is what makes the request folding described above legal.</p>

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
      <p class="lede">YANG Studio ships as a single container that serves both
      the API and the web interface from one process, and it runs as a
      non-root user. All it needs from you is a volume to keep your models
      and device profiles in.</p>

      <h2 id="compose-file">The Compose file</h2>
      <p>If you deploy things locally with Compose, this is the whole file.
      Save it as <code>compose.yaml</code> and run
      <code>docker compose up -d</code>.</p>
      <pre><span class="c"># compose.yaml</span>
services:
  yangstudio:
    image: {IMAGE}:latest
    container_name: yangstudio
    ports:
      <span class="c"># host:container — change the left side if 8420 is taken</span>
      - "8420:8420"
    volumes:
      <span class="c"># Your repositories, sets and device profiles live here.</span>
      <span class="c"># Without this, everything is lost when the container is replaced.</span>
      - yangstudio-data:/data
    environment:
      <span class="c"># Raise this if commits on your devices run long.</span>
      YANGSTUDIO_RPC_TIMEOUT: "120"
    restart: unless-stopped

volumes:
  yangstudio-data:</pre>
      <p>Then open <a href="http://localhost:8420">localhost:8420</a>. There is
      nothing else to configure — no database, no separate web server, and no
      init step.</p>

      <div class="note">
        <p>If you would rather keep the data somewhere you can browse, swap the
        named volume for a directory on the host. The path is relative to the
        Compose file:</p>
        <pre>    volumes:
      - <b>./yangstudio-data</b>:/data</pre>
        <p>This exact file is in the repository as
        <a href="{REPO}/blob/main/compose.yaml">compose.yaml</a>, so you can
        also just clone and run it.</p>
      </div>

      <h2 id="docker">Plain Docker</h2>
      <p>If you are not using Compose, there are two commands worth knowing,
      depending on what you are doing.</p>

      <p>To try it out — it runs in the foreground, and <kbd>Ctrl-C</kbd> stops
      it:</p>
      <pre><b>docker run</b> --rm --name yangstudio \\
  -p 8420:8420 \\
  -v yangstudio-data:/data \\
  {IMAGE}:latest</pre>
      <p><code>--rm</code> removes the container when it stops, so you are not
      left collecting dead containers each time you restart it. It does
      <em>not</em> touch the named volume, so your repositories and device
      profiles survive. <code>--name</code> gives it a predictable name for
      <code>docker logs</code> and <code>docker exec</code>.</p>

      <p>To leave it running — detached, and back after a reboot:</p>
      <pre><b>docker run</b> -d --name yangstudio \\
  --restart unless-stopped \\
  -p 8420:8420 \\
  -v yangstudio-data:/data \\
  {IMAGE}:latest</pre>
      <div class="note">
        <p>These two cannot be combined — Docker rejects
        <code>--rm</code> alongside <code>--restart</code>, since one asks for
        the container to be thrown away and the other asks for it to be brought
        back. Pick whichever matches what you are doing.</p>
      </div>
      <p>The image is built for both <code>linux/amd64</code> and
      <code>linux/arm64</code>, so it runs natively on Apple Silicon as well as
      on ordinary servers. Each build publishes an SBOM and a signed provenance
      attestation alongside it.</p>

      <h2 id="volume">What the volume holds</h2>
      <div class="warn-box">
        <p><b>Make sure <code>/data</code> is mounted somewhere persistent.</b>
        It holds your repositories, your sets and your device profiles. A
        container started without it will work perfectly well, and then lose
        everything the moment it is replaced or upgraded.</p>
      </div>
      <p>The layout inside it is deliberately plain, so you can read, diff and
      version-control the contents without going through the app at all:</p>
      <pre>/data
├── repositories/&lt;name&gt;/*.yang   <span class="c"># plain YANG files</span>
├── yangsets/&lt;name&gt;.json         <span class="c"># which modules, at which revisions</span>
├── devices/&lt;name&gt;.json          <span class="c"># connection profiles</span>
└── cache/                       <span class="c"># header index, safe to delete</span></pre>

      <div class="warn-box">
        <p><b>Device passwords are stored in plain text</b> in
        <code>/data/devices/*.json</code>. They have to be recoverable, because
        the app replays them to authenticate against your devices, so they
        cannot be hashed the way a user password would be. Treat that volume as
        a secret: keep it off shared storage and out of version control.</p>
      </div>

      <h2 id="config">Configuration</h2>
      <p>Every one of these is optional, and the defaults are sensible for a
      local deployment.</p>
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

      <h2 id="memory">How much machine it needs</h2>
      <p>Parsing the models is the expensive part, and the cost scales with the
      set you open rather than with the size of your repository. These
      measurements come from the IETF RFC collection:</p>
      <div class="scroll"><table>
        <thead><tr><th>Operation</th><th>Cost</th></tr></thead>
        <tbody>
          <tr><td>Index a 484-module repository</td><td>0.33 s — headers only</td></tr>
          <tr><td>Parse a 144-module set (11,403 nodes)</td><td>10.9 s</td></tr>
          <tr><td>Re-open the same set</td><td>0.08 s, from cache</td></tr>
          <tr><td>Search across 11,403 nodes</td><td>0.02 s</td></tr>
        </tbody>
      </table></div>
      <p>Large vendor-native models are the memory-hungry case, and a few
      gigabytes is a reasonable allowance if you plan to open those. A handful
      of IETF modules needs very little.</p>

      <h2 id="source">From source</h2>
      <p>Needs <a href="https://docs.astral.sh/uv/">uv</a> and Node 22+.</p>
      <pre>git clone {REPO}
cd yangstudio
./run.sh</pre>
      <p>The script creates the virtual environment, installs the
      dependencies, and finds free ports before starting — 8420 and 5173 are
      both commonly in use — then prints the URLs it settled on.</p>
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
