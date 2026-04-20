# frozen_string_literal: true

# Chair Fabric Randomizer
# SketchUp 2024+ (Ruby 3.x)

require 'json'

module ChurchTools
  module ChairFabricRandomizer
    extend self

    PLUGIN_NAME = 'Chair Fabric Randomizer'

    def run
      model = Sketchup.active_model
      selection = model.selection

      unless model.active_path && !model.active_path.empty?
        UI.messagebox('Open one chair for editing first, then select one labeled target part (example: SEAT BACK).')
        return
      end

      selected_targets = selection.grep(Sketchup::Group) + selection.grep(Sketchup::ComponentInstance)
      if selected_targets.empty?
        UI.messagebox('Select at least one labeled Group or ComponentInstance inside the opened chair.')
        return
      end

      chair_root = detect_chair_root(model.active_path)
      unless chair_root
        UI.messagebox('Could not detect the chair root in the active editing path.')
        return
      end

      source_materials = collect_source_materials(selected_targets)
      if source_materials.empty?
        UI.messagebox('No materials found on selected targets. Paint the sample SEAT BACK/SEAT BOTTOM first, then run again.')
        return
      end

      selected_labels = collect_target_labels(selected_targets)
      settings = prompt_for_settings
      return unless settings

      target_labels = if settings[:target_mode] == 'both'
                        ['SEAT BACK', 'SEAT BOTTOM']
                      else
                        labels = selected_labels
                        labels = prompt_for_target_labels if labels.empty?
                        labels
                      end
      return if target_labels.empty?

      chair_instances = find_candidate_chair_instances(model, chair_root, target_labels)
      if chair_instances.empty?
        UI.messagebox('No chair instances were found with matching target labels. Check your part labels (example: SEAT BACK).')
        return
      end

      variants = build_variant_materials(model, source_materials, settings[:colors], settings[:material_mode])
      if variants.empty?
        UI.messagebox('Could not build material variants from your settings.')
        return
      end

      debug_log(model, chair_root, target_labels, chair_instances, settings)
      debug_variant_summary(variants, settings[:colors].size)

      seed = settings[:seed] || Random.new_seed
      puts("[#{PLUGIN_NAME}] Random seed: #{seed}  (pass this as the seed value to reproduce this layout)")
      color_plan = build_color_plan(chair_instances.size, settings[:colors].size, seed)

      model.start_operation(PLUGIN_NAME, true)
      changed = 0
      color_usage = Hash.new(0)

      begin
        # PHASE 1: Deep make_unique pass over every chair.
        # SketchUp's make_unique is shallow — it only forks the immediate definition.
        # We must recursively make_unique all nested groups/components inside each chair
        # BEFORE touching any materials, otherwise chairs that haven't been processed yet
        # still share sub-definitions with chairs that have, and the last color written wins.
        chair_instances.each do |chair_instance|
          next if chair_instance.deleted?
          deep_make_unique(chair_instance)
        end

        # PHASE 2: Now that every chair and all its children are fully unique,
        # assign colors independently.
        chair_instances.each_with_index do |chair_instance, i|
          next if chair_instance.deleted?

          targets = find_labeled_targets(chair_instance.definition.entities, target_labels)
          next if targets.empty?

          color_index = color_plan[i]
          color_usage[color_index] += 1
          targets.each do |target|
            chosen_variant = variants[color_index % variants.length]
            apply_material_to_target(target, source_materials, chosen_variant)
            changed += 1
          end
        end
      rescue StandardError => e
        model.abort_operation
        UI.messagebox("#{PLUGIN_NAME} failed: #{e.message}")
        raise e
      end

      model.commit_operation
      debug_color_usage(settings[:colors], color_usage)
      UI.messagebox("Updated #{changed} labeled target part(s) across #{chair_instances.size} chair instance(s).")
    end

    private

    def detect_chair_root(active_path)
      return nil if active_path.empty?

      named = active_path.find do |inst|
        n = [safe_name(inst), safe_def_name(inst)].join(' ').downcase
        n.include?('chair')
      end

      named || active_path.first
    end

    def safe_name(instance)
      instance.respond_to?(:name) ? instance.name.to_s : ''
    end

    def safe_def_name(instance)
      instance.respond_to?(:definition) ? instance.definition.name.to_s : ''
    end

    def collect_source_materials(instances)
      mats = []
      instances.each do |inst|
        mats << inst.material if inst.material
        gather_face_materials(inst.definition.entities, mats)
      end
      mats.compact.uniq
    end

    def gather_face_materials(entities, out)
      entities.grep(Sketchup::Face).each do |face|
        out << face.material if face.material
        out << face.back_material if face.back_material
      end

      nested = entities.grep(Sketchup::Group) + entities.grep(Sketchup::ComponentInstance)
      nested.each { |inst| gather_face_materials(inst.definition.entities, out) }
    end

    def collect_target_labels(instances)
      labels = instances.map do |inst|
        name = safe_name(inst).strip
        name.empty? ? safe_def_name(inst).strip : name
      end
      labels.map(&:upcase).reject(&:empty?).uniq
    end

    def prompt_for_target_labels
      input = UI.inputbox(
        ['Target part label(s), comma-separated (example: SEAT BACK, SEAT BOTTOM):'],
        ['SEAT BACK'],
        'Chair part labels'
      )
      return [] unless input

      input.first.to_s.split(',').map { |s| s.strip.upcase }.reject(&:empty?).uniq
    end

    def find_labeled_targets(entities, target_labels, out = [])
      items = entities.grep(Sketchup::Group) + entities.grep(Sketchup::ComponentInstance)
      items.each do |inst|
        nm = safe_name(inst).strip.upcase
        dn = safe_def_name(inst).strip.upcase

        out << inst if target_labels.include?(nm) || target_labels.include?(dn)

        find_labeled_targets(inst.definition.entities, target_labels, out)
      end
      out
    end

    # Search for chair instances by finding the broadest organizer group that
    # still makes sense — i.e. the outermost ancestor in the active_path whose
    # name/def suggests it is the "CHAIRS" container (or a section/row of them).
    # We walk the active_path from outermost to innermost and take the last
    # ancestor whose entities contain chairs, so we always get the widest net.
    def find_candidate_chair_instances(model, chair_root, target_labels)
      active_path = model.active_path || []

      # Log every ancestor so we can see the full path in the console
      active_path.each_with_index do |inst, i|
        puts("[#{PLUGIN_NAME}] active_path[#{i}]: '#{safe_name(inst)}' / '#{safe_def_name(inst)}'")
      end

      # Walk active_path outermost→innermost and collect ALL ancestors whose
      # entities contain at least one chair with the target labels.
      # We want the outermost (first) hit — that gives us the widest search scope.
      best = nil
      active_path.each do |inst|
        next unless inst.respond_to?(:definition)
        lbl = "#{safe_name(inst)}/#{safe_def_name(inst)}"
        candidates = collect_chair_instances_shallow(inst.definition.entities, target_labels, depth: 0)
        puts("[#{PLUGIN_NAME}] Checking ancestor '#{lbl}': #{candidates.size} chair(s)")
        if best.nil? && !candidates.empty?
          best = [lbl, candidates]
        end
      end

      if best
        puts("[#{PLUGIN_NAME}] Using outermost ancestor with chairs: '#{best[0]}' → #{best[1].size} chair(s)")
        return best[1]
      end

      # Fallback: try model.active_entities, then model.entities
      [
        ['active_entities', model.active_entities],
        ['model.entities', model.entities]
      ].each do |lbl, entities|
        candidates = collect_chair_instances_shallow(entities, target_labels, depth: 0)
        unless candidates.empty?
          puts("[#{PLUGIN_NAME}] Found #{candidates.size} chair(s) in #{lbl}")
          return candidates
        end
      end

      puts("[#{PLUGIN_NAME}] All search roots exhausted; falling back to chair_root.")
      [chair_root]
    end

    # Traverse into Groups only (organizer layers like CHAIRS / CENTER SECTION / ROW 1).
    # When we find a ComponentInstance whose name/def includes 'chair' and contains
    # the target labels, collect it as-is — do NOT recurse into its definition,
    # because all chairs share that same definition and recursing would yield
    # duplicate references to the same Ruby objects.
    def collect_chair_instances_shallow(entities, target_labels, depth:)
      out = []
      items = entities.grep(Sketchup::Group) + entities.grep(Sketchup::ComponentInstance)

      items.each do |inst|
        name_combined = [safe_name(inst), safe_def_name(inst)].join(' ').downcase

        if name_combined.include?('chair') && contains_target_label?(inst.definition.entities, target_labels)
          # This is a chair instance — collect it, do not recurse inside
          out << inst
        elsif inst.is_a?(Sketchup::Group) && depth < 6
          # This is an organizer group (CHAIRS, CENTER SECTION, ROW 1, etc.)
          # Safe to recurse because Groups have unique entity collections
          out.concat(collect_chair_instances_shallow(inst.definition.entities, target_labels, depth: depth + 1))
        end
        # ComponentInstances that are NOT chairs are skipped entirely —
        # recursing into them would re-visit the shared definition
      end

      out.uniq
    end

    def contains_target_label?(entities, target_labels)
      items = entities.grep(Sketchup::Group) + entities.grep(Sketchup::ComponentInstance)
      items.any? do |inst|
        nm = safe_name(inst).strip.upcase
        dn = safe_def_name(inst).strip.upcase
        target_labels.include?(nm) || target_labels.include?(dn) || contains_target_label?(inst.definition.entities, target_labels)
      end
    end

    # Assign a color index to each chair using a seeded RNG.
    # Each chair independently draws a random color rather than shuffling a
    # balanced deck — this prevents rows of the same size from producing
    # mirror-image patterns, which happened because balanced shuffles of the
    # same deck size tend to rhyme visually.
    # The seed is logged to the console so a pleasing result can be reproduced
    # by entering the same seed value in the settings dialog.
    def build_color_plan(chair_count, color_count, seed)
      rng = Random.new(seed)
      Array.new(chair_count) { rng.rand(color_count) }
    end

    def debug_variant_summary(variants, expected_count)
      puts("[#{PLUGIN_NAME}] Variant count generated: #{variants.length}, expected=#{expected_count}")

      variants.each_with_index do |variant, i|
        tex = variant.texture ? 'yes' : 'no'
        mtype = variant.respond_to?(:materialType) ? variant.materialType : 'n/a'
        puts("[#{PLUGIN_NAME}] Variant #{i + 1}: name='#{variant.display_name}', texture=#{tex}, color=#{variant.color}, materialType=#{mtype}")
      end
    end

    def debug_color_usage(colors, color_usage)
      mapped = colors.each_with_index.map do |c, i|
        hex = format('#%02X%02X%02X', c.red, c.green, c.blue)
        "#{hex}=#{color_usage[i] || 0}"
      end
      puts("[#{PLUGIN_NAME}] Color usage by chair: #{mapped.join(', ')}")
    end

    def debug_log(model, chair_root, target_labels, chair_instances, settings)
      puts("[#{PLUGIN_NAME}] Model: #{model.title}")
      puts("[#{PLUGIN_NAME}] Active root: #{safe_name(chair_root)} / #{safe_def_name(chair_root)}")
      puts("[#{PLUGIN_NAME}] Target labels: #{target_labels.join(', ')}")
      puts("[#{PLUGIN_NAME}] Candidate chairs found: #{chair_instances.size}")
      puts("[#{PLUGIN_NAME}] Colors selected: #{settings[:colors].map { |c| format('#%02X%02X%02X', c.red, c.green, c.blue) }.join(', ')}")
      puts("[#{PLUGIN_NAME}] Material mode: #{settings[:material_mode]}")
      puts("[#{PLUGIN_NAME}] Target mode: #{settings[:target_mode]}")
    end

    def prompt_for_settings
      return fallback_settings_prompt unless defined?(UI::HtmlDialog)

      dialog = UI::HtmlDialog.new(
        dialog_title: 'Choose Random Fabric Palette',
        preferences_key: 'ChairFabricRandomizerPalette',
        scrollable: true,
        resizable: false,
        width: 500,
        height: 560,
        style: UI::HtmlDialog::STYLE_DIALOG
      )

      html = <<~HTML
        <!doctype html>
        <html>
        <head>
          <meta charset="UTF-8" />
          <style>
            body { font-family: Arial, sans-serif; margin: 14px; }
            h3 { margin: 0 0 10px; }
            .section { margin-bottom: 14px; border: 1px solid #ddd; border-radius: 6px; padding: 10px; }
            .count { display: flex; gap: 12px; margin-bottom: 8px; }
            .color-row { margin: 8px 0; display: flex; align-items: center; gap: 10px; }
            .help { color: #555; font-size: 12px; }
            button { margin-top: 12px; padding: 8px 12px; }
          </style>
        </head>
        <body>
          <div class="section">
            <h3>Color count</h3>
            <div class="count">
              <label><input type="radio" name="count" value="2" checked> 2 colors</label>
              <label><input type="radio" name="count" value="3"> 3 colors</label>
              <label><input type="radio" name="count" value="4"> 4 colors</label>
            </div>
            <div id="colors"></div>
          </div>

          <div class="section">
            <h3>Material behavior</h3>
            <label><input type="radio" name="materialMode" value="colorize" checked> Colorize existing texture image</label><br>
            <label><input type="radio" name="materialMode" value="solid"> Replace with solid color (remove texture)</label>
          </div>

          <div class="section">
            <h3>Target behavior</h3>
            <label><input type="radio" name="targetMode" value="selected" checked> Just change selected element label(s)</label><br>
            <label><input type="radio" name="targetMode" value="both"> Apply together to SEAT BACK + SEAT BOTTOM</label>
            <div class="help">When "both" is selected, each chair gets one random color and both parts match each other.</div>
          </div>

          <div class="section">
            <h3>Random seed <span class="help">(optional)</span></h3>
            <div class="color-row">
              <input type="number" id="seedInput" placeholder="leave blank for random" style="width:200px;padding:4px;">
            </div>
            <div class="help">The seed used is always logged to the Ruby Console. Enter it here to reproduce a previous layout exactly.</div>
          </div>

          <button onclick="submitSettings()">Apply</button>
          <button onclick="sketchup.cancel()" style="margin-left:8px;">Cancel</button>

          <script>
            const defaults = ['#8d3f3f', '#3f5f8d', '#5c7a52', '#6f4f8e'];

            function selectedCount() {
              return parseInt(document.querySelector('input[name="count"]:checked').value, 10);
            }

            function renderPickers() {
              const count = selectedCount();
              const holder = document.getElementById('colors');
              holder.innerHTML = '';

              for (let i = 0; i < count; i++) {
                const row = document.createElement('div');
                row.className = 'color-row';
                row.innerHTML = `<label>Color ${i + 1}</label><input type="color" value="${defaults[i]}">`;
                holder.appendChild(row);
              }
            }

            function submitSettings() {
              const rawSeed = document.getElementById('seedInput').value.trim();
              const payload = {
                colors: Array.from(document.querySelectorAll('#colors input[type="color"]')).map(i => i.value),
                material_mode: document.querySelector('input[name="materialMode"]:checked').value,
                target_mode: document.querySelector('input[name="targetMode"]:checked').value,
                seed: rawSeed === '' ? null : parseInt(rawSeed, 10)
              };
              sketchup.apply(JSON.stringify(payload));
            }

            document.querySelectorAll('input[name="count"]').forEach(r => r.addEventListener('change', renderPickers));
            renderPickers();
          </script>
        </body>
        </html>
      HTML

      result = nil
      dialog.add_action_callback('apply') do |_ctx, json|
        begin
          payload = JSON.parse(json)
          result = parse_settings_payload(payload)
        rescue StandardError
          result = nil
        end
        dialog.close
      end

      dialog.add_action_callback('cancel') do |_ctx|
        result = nil
        dialog.close
      end

      dialog.set_html(html)
      dialog.show_modal
      result
    end

    def fallback_settings_prompt
      prompts = [
        'Number of colors (2-4):',
        'Hex colors comma-separated (#ff0000,#00ff00):',
        'Material mode (colorize or solid):',
        'Target mode (selected or both):',
        'Seed (leave 0 for random):',
      ]
      values = ['2', '#8d3f3f, #3f5f8d', 'colorize', 'selected', '0']
      input = UI.inputbox(prompts, values, 'Choose random fabric settings')
      return nil unless input

      count = input[0].to_i
      return nil unless (2..4).include?(count)

      colors = input[1].to_s.split(',').map { |hex| hex_to_color(hex) }.compact
      colors = colors.uniq
      return nil if colors.size < count

      mode = input[2].to_s.strip.downcase
      mode = 'colorize' unless %w[colorize solid].include?(mode)

      target_mode = input[3].to_s.strip.downcase
      target_mode = 'selected' unless %w[selected both].include?(target_mode)

      raw_seed = input[4].to_i
      seed = raw_seed > 0 ? raw_seed : nil

      {
        colors: colors.first(count),
        material_mode: mode,
        target_mode: target_mode,
        seed: seed
      }
    end

    def parse_settings_payload(payload)
      colors = Array(payload['colors']).map { |hex| hex_to_color(hex) }.compact.uniq
      return nil if colors.size < 2

      material_mode = payload['material_mode'].to_s
      material_mode = 'colorize' unless %w[colorize solid].include?(material_mode)

      target_mode = payload['target_mode'].to_s
      target_mode = 'selected' unless %w[selected both].include?(target_mode)

      raw_seed = payload['seed']
      seed = raw_seed.is_a?(Integer) && raw_seed > 0 ? raw_seed : nil

      {
        colors: colors,
        material_mode: material_mode,
        target_mode: target_mode,
        seed: seed
      }
    end

    def hex_to_color(hex)
      h = hex.to_s.strip
      h = "##{h}" unless h.start_with?('#')
      return nil unless h.match?(/^#[0-9a-fA-F]{6}$/)

      r = h[1..2].to_i(16)
      g = h[3..4].to_i(16)
      b = h[5..6].to_i(16)
      Sketchup::Color.new(r, g, b)
    end

    def build_variant_materials(model, source_materials, colors, material_mode)
      base_source = source_materials.first
      return [] unless base_source

      variants = colors.map.with_index do |color, idx|
        find_or_create_variant_material(model, base_source, color, idx, material_mode)
      end.compact

      if variants.length < colors.length
        puts("[#{PLUGIN_NAME}] Warning: base source '#{base_source.display_name}' produced only #{variants.length}/#{colors.length} variants.")
      end

      variants
    end

    def find_or_create_variant_material(model, source, color, idx, material_mode)
      hex = format('%02X%02X%02X', color.red, color.green, color.blue)
      base = source.display_name.to_s.strip
      base = 'Fabric' if base.empty?
      safe = base.gsub(/[^0-9A-Za-z_\-]/, '_')
      name = "CFR_#{material_mode}_#{safe}_#{idx + 1}_#{hex}"

      mat = model.materials[name] || model.materials.add(name)
      mat.alpha = source.alpha if source.respond_to?(:alpha)

      if material_mode == 'colorize' && source.texture
        begin
          copy_texture(source, mat)
          raise 'Texture copy failed.' unless mat.texture
          # Set the color tint directly. SketchUp will display the texture
          # with this hue overlay (materialType becomes 2 = colorized texture).
          # Do NOT bake — baking unreliably resets the color to white.
          mat.color = color
        rescue StandardError => e
          puts("[#{PLUGIN_NAME}] Texture colorize fallback for '#{source.display_name}': #{e.message}")
          mat.color = color
        end
      else
        mat.texture = nil if mat.texture
        mat.color = color
      end

      mat
    rescue StandardError => e
      puts("[#{PLUGIN_NAME}] Failed to create variant '#{source.display_name}' #{hex}: #{e.message}")
      nil
    end

    def copy_texture(source, destination)
      texture = source.texture
      return unless texture

      if texture.respond_to?(:filename) && texture.filename && !texture.filename.empty? && File.exist?(texture.filename)
        destination.texture = texture.filename
      elsif texture.respond_to?(:image_rep)
        image_rep = texture.image_rep
        destination.texture = image_rep if image_rep
      end

      if destination.texture && texture.respond_to?(:size)
        destination.texture.size = texture.size
      end
    end

    # Recursively make_unique an instance and all nested groups/components.
    # Must be called on every chair BEFORE any material assignment so that
    # no two chairs share any sub-definition when colors are applied.
    def deep_make_unique(instance)
      return unless instance.respond_to?(:make_unique) && instance.respond_to?(:definition)
      instance.make_unique
      items = instance.definition.entities.grep(Sketchup::Group) +
              instance.definition.entities.grep(Sketchup::ComponentInstance)
      items.each { |child| deep_make_unique(child) }
    end

    # Apply a material to a target instance and all faces inside it.
    # By the time this is called, deep_make_unique has already been run so
    # no make_unique calls are needed here.
    def apply_material_to_target(instance, source_materials, variant_material)
      instance.material = variant_material if source_materials.include?(instance.material)
      replace_materials(instance.definition.entities, source_materials, variant_material)
    end

    def replace_materials(entities, source_materials, variant_material)
      entities.grep(Sketchup::Face).each do |face|
        face.material = variant_material if source_materials.include?(face.material)
        face.back_material = variant_material if source_materials.include?(face.back_material)
      end

      nested = entities.grep(Sketchup::Group) + entities.grep(Sketchup::ComponentInstance)
      nested.each do |inst|
        inst.material = variant_material if source_materials.include?(inst.material)
        replace_materials(inst.definition.entities, source_materials, variant_material)
      end
    end

    unless file_loaded?(__FILE__)
      UI.menu('Extensions').add_item(PLUGIN_NAME) { run }
      file_loaded(__FILE__)
    end
  end
end
